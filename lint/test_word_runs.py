#!/usr/bin/env python3
"""Fixture test for the one fence reader of lint/word_runs.py. Run: python3 lint/test_word_runs.py -v

word_runs is the one home of what a fence is. A fence line indented four spaces or more is a fence only under a list
item; at the top level such a line is indented code (CommonMark), and so is the block it opens. Each check that reads
fences calls the one home and holds no fence walk of its own. Stdlib unittest; no file is read or written. Rule
building-one-home-per-capability.
"""
import ast
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
# A top-level block opened by an indented fence line, with a row inside it indented the same way (CommonMark code).
TOP_LEVEL_BLOCKS = (("    ```", "    hidden text"), ("\t```", "\thidden text"), ("    ~~~", "    hidden text"))

# The modules that read fences. Each reads its rows through word_runs.code_mask, and none asks is_fence line by line.
FENCE_CALLERS = ("ste_lint.py", "check_ruling_kind.py", "hook_catalog.py", "find_copies.py", "stale_cites.py",
                 "compliance_probes.py", "check_skill_model_rows.py", os.path.join("..", "hooks", "feedback_guard.py"))
FENCE_CALLS = ("compile", "match", "fullmatch", "search", "sub", "finditer")
FENCE_MARKS = ("```", "~~~")


class FenceLineTests(unittest.TestCase):
    def test_a_fence_line_indented_four_spaces_or_more_is_a_fence(self):
        missed = [line for line in DEEP_FENCES if word_runs.FENCE.match(line) is None]
        self.assertEqual(missed, [], "word_runs.FENCE misses a fence line indented four spaces or more; it reads three "
                                     "spaces at most")

    def test_a_fence_line_of_three_spaces_or_less_is_a_fence_and_prose_is_not(self):
        self.assertEqual([line for line in SHALLOW_FENCES if word_runs.FENCE.match(line) is None], [], "control")
        self.assertEqual([line for line in NOT_FENCES if word_runs.FENCE.match(line) is not None], [], "control")


class OneFenceHomeTests(unittest.TestCase):
    def test_fence_readers_on_the_one_home_hold_no_fence_pattern_of_their_own(self):
        # check_skill_model_rows and feedback_guard read the one fence line. Their imports are here, not at the top,
        # so the other readers stay importable when a hook's import fails.
        hooks = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks")
        if hooks not in sys.path:
            sys.path.insert(0, hooks)
        import check_skill_model_rows
        import feedback_guard
        for module in (stale_cites, compliance_probes, check_skill_model_rows, feedback_guard):
            with self.subTest(module=module.__name__):
                # An alias of the one home is allowed and may be dropped; a FENCE of its own is not.
                alias = getattr(module, "FENCE", word_runs.FENCE)
                self.assertIs(alias, word_runs.FENCE,
                              "%s holds its own FENCE regex; it may only alias word_runs.FENCE" % module.__name__)
                # A fence pattern under another name is a copy too.
                renamed = [name for name, value in vars(module).items() if isinstance(value, re.Pattern)
                           and value is not word_runs.FENCE and any(value.match(line) for line in DEEP_FENCES)]
                self.assertEqual(renamed, [], "%s holds a fence pattern of its own under another name" % module.__name__)
        # ste_lint's FENCE is read nowhere. It goes as a delete, or as an alias of the one home; never as its own pattern.
        import ste_lint
        self.assertIs(getattr(ste_lint, "FENCE", word_runs.FENCE), word_runs.FENCE,
                      "ste_lint holds a FENCE of its own that nothing reads; delete it")


class ListAwareFenceTests(unittest.TestCase):
    def test_is_fence_four_spaces_is_a_fence_only_inside_a_list_item(self):
        self.assertTrue(hasattr(word_runs, "is_fence"), "word_runs has no is_fence")  # the scope first
        with self.subTest(case="top level, four spaces"):
            self.assertFalse(word_runs.is_fence("    ```", in_list_item=False),
                             "a top-level four-space fence line is indented code, not a fence")
        with self.subTest(case="top level, a tab"):
            self.assertFalse(word_runs.is_fence("\t```", in_list_item=False), "a top-level tab-led line is indented code")
        with self.subTest(case="list item, four spaces"):
            self.assertTrue(word_runs.is_fence("    ```", in_list_item=True),
                            "a four-space fence line inside a list item is a fence")
        with self.subTest(case="list item, four spaces, prose"):
            self.assertFalse(word_runs.is_fence("    text", in_list_item=True), "an indented line of text is no fence")

    def test_is_fence_up_to_three_spaces_is_a_fence_either_way(self):
        self.assertTrue(hasattr(word_runs, "is_fence"), "word_runs has no is_fence")
        for line in ("```", "   ```", "~~~", "   ~~~"):
            for in_item in (False, True):
                with self.subTest(line=line, in_list_item=in_item):
                    self.assertTrue(word_runs.is_fence(line, in_list_item=in_item),
                                    "a fence line indented three spaces or less is a fence in or out of a list item")

    def test_units_and_mask_fences_do_not_open_a_fence_at_top_level_four_spaces(self):
        text = "Prose before the fence line.\n\n    ```\nProse after the fence line.\n"
        with self.subTest(case="mask_fences"):
            self.assertIn("Prose after the fence line.", word_runs.mask_fences(text),
                          "a top-level four-space fence line in prose opened a fence, which hid the prose after it")
        with self.subTest(case="units"):
            prose = [unit for _, unit in word_runs.units(text) if "Prose after the fence line." in unit]
            self.assertTrue(prose and all("```" not in unit for unit in prose),
                            "a top-level four-space fence line in prose made the prose after it part of a fenced unit")
        # Control: the same shape inside a list item is a fence, so its text is hidden.
        listed = "1. Step one:\n\n    ```sh\nInside the fence.\n    ```\nAfter the fence.\n"
        with self.subTest(case="control, list item"):
            self.assertNotIn("Inside the fence.", word_runs.mask_fences(listed), "a list-item fence hides its text")
            self.assertIn("After the fence.", word_runs.mask_fences(listed), "the prose after a list-item fence is read")


class TopLevelIndentedBlockTests(unittest.TestCase):
    def test_a_top_level_indented_fence_block_hides_the_rows_inside_it(self):
        # CommonMark: a top-level block indented four spaces or led by a tab is code. A fence on main hid these rows, so
        # the same rows hide in mask_fences now. The prose after the block is read.
        for opener, row in TOP_LEVEL_BLOCKS:
            with self.subTest(opener=opener):
                text = "Prose before.\n\n%s\n%s\n%s\n\nProse after.\n" % (opener, row, opener)
                masked = word_runs.mask_fences(text)
                self.assertNotIn(row.strip(), masked,
                                 "a top-level block opened by %r is indented code and must hide its rows" % opener)
                self.assertIn("Prose after.", masked, "the prose after a top-level %r block is read" % opener)

    def test_a_top_level_indented_block_is_its_own_unit(self):
        # The prose after the block is not part of it: a rule id in that prose must not exempt a copy inside the block.
        text = "Prose before.\n\n    ```\n    hidden text\n    ```\nAfter the block.\n"
        with_block = [unit for _, unit in word_runs.units(text) if "hidden text" in unit]
        self.assertTrue(with_block, "the block's rows are in no unit")
        self.assertTrue(all("After the block." not in unit for unit in with_block),
                        "the prose after a top-level indented block is read as part of the block's unit")
        # Control: the same prose after a list-item fence is no part of that fence either.
        listed = "1. Step one:\n\n    ```sh\n    hidden text\n    ```\nAfter the block.\n"
        listed_units = [unit for _, unit in word_runs.units(listed) if "hidden text" in unit]
        with self.subTest(case="control, list item"):
            self.assertTrue(listed_units and all("After the block." not in unit for unit in listed_units),
                            "the prose after a list-item fence is read as part of the fence's unit")


def masked(text, only=None):
    """word_runs.mask_code_spans of `text`, with `only` passed on. The name is checked first, so a missing name fails
    with its own message."""
    if not hasattr(word_runs, "mask_code_spans"):
        raise AssertionError("word_runs has no mask_code_spans")
    return word_runs.mask_code_spans(text, only=only)


def assert_same_shape(case, text, expected, cause):
    """mask_code_spans(text) matches `expected` with each mask character read as a space. A claim about where a span
    sits does not depend on the mask character; the NUL case holds that."""
    case.assertEqual(masked(text).replace("\0", " "), expected.replace("\0", " "), cause)


class MaskCodeSpansTests(unittest.TestCase):
    """mask_code_spans, the masker of inline code for a reader that keeps line and word positions (the report guard's
    model-name check). A span becomes NUL characters, so a reader never reads a word inside it."""

    def test_a_lone_backtick_masks_nothing(self):
        for text in ("Done ` alone, with no closer.", "Don't stop ` here."):
            with self.subTest(text=text):
                self.assertEqual(masked(text), text, "a lone backtick opened a span")

    def test_a_comment_opener_inside_a_span_is_masked_with_it(self):
        for opener in ("/*", "//", "#"):
            with self.subTest(opener=opener):
                span = "`a %s b`" % opener
                assert_same_shape(self, "x %s y" % span, "x " + "\0" * len(span) + " y",
                                  "a %r inside a span was not masked with its span" % opener)
        # Control: the same openers outside a span are plain text and stay as they are.
        for text, expected in (("a // b `c` d", "a // b " + "\0" * 3 + " d"),
                               ("# Heading `x` here", "# Heading " + "\0" * 3 + " here"),
                               ("a /* b `c` d", "a /* b " + "\0" * 3 + " d")):
            with self.subTest(text=text):
                assert_same_shape(self, text, expected, "text outside a span changed")

    def test_a_multi_line_span_keeps_its_line_break(self):
        assert_same_shape(self, "a `one\ntwo` b", "a " + "\0" * 4 + "\n" + "\0" * 4 + " b",
                          "a span over two lines was not masked whole, with its line break kept")

    def test_a_span_stops_at_a_blank_line(self):
        # Control: the same span with no blank line between its halves is masked, so the blank line is what stops it.
        assert_same_shape(self, "a `one\ntwo` b", "a " + "\0" * 4 + "\n" + "\0" * 4 + " b",
                          "a span over two lines was not masked whole, with its line break kept")
        for text in ("a `one\n\ntwo` b", "a `one\n  \ntwo` b"):
            with self.subTest(text=text):
                self.assertEqual(masked(text), text, "a span crossed a blank line")

    def test_output_length_equals_input_length(self):
        rows = ("", "plain text", "a `x` b", "`a\nb` and `c`", "Done (builder `x` sonnet), see `f` (D12).",
                "a ` lone", "x <!-- c --> `y` // z", "`hold-unsafe-x` (net-value hold) and `/* open",
                "ünï `cödé`")
        for text in rows:
            with self.subTest(text=text):
                self.assertEqual(len(masked(text)), len(text), "the mask changed the length of the text")

    def test_masked_characters_are_nul_never_spaces(self):
        self.assertEqual(masked("builder `x` sonnet"), "builder " + "\0" * 3 + " sonnet",
                         "a span is not masked as one NUL per character")
        self.assertEqual(masked("builder `x y` sonnet"), "builder " + "\0" * 5 + " sonnet",
                         "a space inside a span was not masked as a NUL")
        runs = re.findall(r"[a-z]+|\0+", masked("builder `x` sonnet"))
        self.assertEqual(runs, ["builder", "\0" * 3, "sonnet"],
                         "the span does not stand between its two words as a run of its own")

    def test_an_only_pattern_masks_a_span_in_a_gloss_after_a_span_that_holds_no_match(self):
        # `foo` holds no match, so it stays readable. The span in its gloss holds one, so it is masked.
        self.assertEqual(masked("`foo` (see `reviewer opus`)", only=re.compile("reviewer")),
                         "`foo` (see " + "\0" * 15 + ")",
                         "a span in the gloss after a span that holds no match was not masked")

    def test_a_gloss_with_no_inner_span_is_returned_unchanged(self):
        self.assertEqual(masked("`foo` (see the reviewer)", only=re.compile("reviewer")), "`foo` (see the reviewer)",
                         "a gloss with no inner span changed under an only pattern")
        self.assertEqual(masked("`foo` (see the reviewer)"), "\0" * 5 + " (see the reviewer)",
                         "a gloss with no inner span changed")

    def test_a_leading_span_that_holds_a_match_is_masked_whole_with_its_gloss_kept(self):
        self.assertEqual(masked("`reviewer opus` (see the reviewer)", only=re.compile("reviewer")),
                         "\0" * 15 + " (see the reviewer)",
                         "a leading span that holds a match was not masked whole, or its gloss changed")

    def test_a_span_in_a_gloss_after_a_span_is_masked_without_an_only_pattern(self):
        # Without `only`, both spans are masked. The plain words of the gloss stay readable.
        self.assertEqual(masked("`foo` (see `reviewer opus`)"), "\0" * 5 + " (see " + "\0" * 15 + ")",
                         "a span inside the gloss of another span was not masked when no only pattern is given")

    def test_a_gloss_span_that_fails_only_stays_readable(self):
        # `sonnet` fails the only pattern, so it stays readable, as the leading `foo` does.
        self.assertEqual(masked("`foo` (see `sonnet`)", only=re.compile("reviewer")), "`foo` (see `sonnet`)",
                         "a span in a gloss that fails the only pattern was masked")


class FenceCallersTests(unittest.TestCase):
    def test_each_fence_caller_reads_its_rows_through_code_mask(self):
        # Not built yet: word_runs.code_mask is the claim the callers read through (R1). Each caller is one subtest.
        lint = os.path.dirname(os.path.abspath(__file__))
        for name in FENCE_CALLERS:
            with self.subTest(module=name):
                tree = _tree(lint, name)
                self.assertTrue(_calls(tree, "code_mask"), "%s does not call word_runs.code_mask" % name)

    def test_no_fence_caller_asks_is_fence_line_by_line(self):
        lint = os.path.dirname(os.path.abspath(__file__))
        for name in FENCE_CALLERS:
            with self.subTest(module=name):
                lines = _calls(_tree(lint, name), "is_fence")
                self.assertEqual(lines, [], "%s asks word_runs.is_fence line by line at lines %s; read word_runs.code_mask "
                                            "instead" % (name, lines))

    def test_no_fence_caller_toggles_a_fence_on_a_startswith_of_a_fence_mark(self):
        # The indent rule is lost in a startswith on the stripped line: it reads a four-space fence line as a fence.
        lint = os.path.dirname(os.path.abspath(__file__))
        for name in FENCE_CALLERS:
            with self.subTest(module=name):
                lines = _fence_toggles(_tree(lint, name))
                self.assertEqual(lines, [], "%s toggles a fence on startswith of a fence mark at lines %s; use "
                                            "word_runs.code_mask" % (name, lines))

    def test_no_fence_caller_holds_a_fence_regex_of_its_own(self):
        lint = os.path.dirname(os.path.abspath(__file__))
        for name in FENCE_CALLERS:
            with self.subTest(module=name):
                # A fence pattern carries a tilde, so a backtick-only pattern (feedback_guard's closer check) is no copy.
                regexes = [node.lineno for node in ast.walk(_tree(lint, name)) if isinstance(node, ast.Call)
                           and isinstance(node.func, ast.Attribute) and node.func.attr in FENCE_CALLS
                           and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)
                           and "~" in node.args[0].value and any(mark in node.args[0].value for mark in ("{3,}", "```", "~~~"))]
                self.assertEqual(regexes, [], "%s holds a fence regex of its own, on the lines listed" % name)


def _tree(lint, name):
    with open(os.path.join(lint, name), encoding="utf-8") as handle:
        return ast.parse(handle.read(), name)


def _calls(tree, name):
    """Line numbers of each call of `name`, as an attribute or a bare name."""
    return [node.lineno for node in ast.walk(tree) if isinstance(node, ast.Call)
            and ((isinstance(node.func, ast.Attribute) and node.func.attr == name)
                 or (isinstance(node.func, ast.Name) and node.func.id == name))]


def _fence_toggles(tree):
    """Line numbers of each startswith or endswith call whose argument is a fence mark, or a tuple holding one."""
    def holds_mark(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return any(mark in node.value for mark in FENCE_MARKS)
        if isinstance(node, ast.Tuple):
            return any(holds_mark(elt) for elt in node.elts)
        return False
    return [node.lineno for node in ast.walk(tree) if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute) and node.func.attr in ("startswith", "endswith")
            and node.args and holds_mark(node.args[0])]


if __name__ == "__main__":
    unittest.main()
