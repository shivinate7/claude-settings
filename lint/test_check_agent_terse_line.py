#!/usr/bin/env python3
"""Fixture suite for lint/check_agent_terse_line.py. Run: python3 lint/test_check_agent_terse_line.py

Each agent role file (the ten named roles, and any other agents/*.md) and the lane start text
(skills/project-ops/templates/operating-model.md) must hold TERSE_LINE, the one short-output line the
check exports. The line counts as body text only. A line inside a code fence (``` or ~~~), an HTML
comment, a code span or a 4-space indented code block does not count, and neither does a line in an
agent file's frontmatter. A code span stays inside one paragraph. A list item's 4-space continuation
counts. A comment opener inside inline code opens nothing, even across a line break. A fence marker
in the middle of a line opens nothing. A lone quote in prose hides nothing, and a lone backtick does
not pair across a blank line. A comment opened mid-line ends at its paragraph break, and a comment opened at a
line start hides the rest of the line it closes on. The line may wrap over a line break. A heading, a fence, a list
item, a quote or a rule line ends a comment opened mid-line above it. A line-start comment ends the paragraph above
it, and a rule line (`---`, `* * *`, `- - -`) is not a list item: it clears the list above it. The scan's cost grows
no faster than linear, and a paragraph with one lone backtick and no close is not searched.
A file that cannot be read is unknown (exit 2, named), never clear.

The no-argument run reads the module's ROOT when it runs. These cases patch ROOT to a fixture tree.
"""
import contextlib, io, os, shutil, sys, tempfile, unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import check_agent_terse_line as C  # noqa: E402  the check and the one home of TERSE_LINE
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (the one home, lint/_test_temp.py)
# The sweep of old run folders is proved once, in lint/test_find_copies.py, so this suite does not repeat it.
RUN_FOLDER = _test_temp.run_folder()

TERSE_LINE = C.TERSE_LINE
# The ten role files the brief names. A deleted one is a finding, so the list is pinned here, not read from agents/.
ROLES = ("builder", "claude-code-guide", "design-reviewer", "designer", "explore",
         "plan", "record-writer", "refuter", "reviewer", "test-author")
LANE_TEXT = os.path.join("skills", "project-ops", "templates", "operating-model.md")


def doc(body, front="name: fixture"):
    """A file with frontmatter, then the body. front is the frontmatter's lines; None writes no frontmatter."""
    if front is None:
        return "# Fixture\n\n%s\n" % body
    return "---\n%s\n---\n# Fixture\n\n%s\n" % (front, body)


def long_prose(count=3000):
    """A body of count prose lines: the full-size state of a fixture."""
    return "\n".join("Prose line %d of the file." % n for n in range(count))


def fixture_root():
    """A new folder under this run's folder. The run folder's teardown removes it."""
    return tempfile.mkdtemp(dir=RUN_FOLDER)


def write(root, relpath, text):
    path = os.path.join(root, relpath)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def check_files(*paths):
    """The check's (exit code, stdout). With no path, the no-argument run."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = C.main(list(paths))
    return code, out.getvalue()


def names(out, filename):
    """The output lines that name the file."""
    return [line for line in out.splitlines() if filename in line]


def wrapped(text):
    """The line split over a line break at a word boundary, as a paragraph wraps."""
    words = text.split(" ")
    mid = len(words) // 2
    return " ".join(words[:mid]) + "\n" + " ".join(words[mid:])


class TerseLineText(unittest.TestCase):
    def test_the_line_says_reasoning_is_never_cut(self):
        self.assertIn("reasoning", TERSE_LINE.lower(), "TERSE_LINE does not say that reasoning is never cut")

    def test_the_line_says_tool_inputs_are_never_cut(self):
        self.assertIn("tool input", TERSE_LINE.lower(), "TERSE_LINE does not say that tool inputs are never cut")

    def test_the_line_is_one_nonblank_line(self):
        self.assertTrue(TERSE_LINE.strip(), "TERSE_LINE is blank")
        self.assertNotIn("\n", TERSE_LINE, "TERSE_LINE spans more than one line")


class BodyCases:
    """The cases for one file's body. A subclass sets NAME, the file's path under the fixture root."""
    NAME = None

    def verdict(self, body, **opts):
        root = fixture_root()
        return check_files(write(root, self.NAME, doc(body, **opts)))

    def test_a_file_with_the_line_passes(self):
        self.assertEqual(self.verdict("Work the brief.\n\n" + TERSE_LINE), (0, ""),
                         "a file that holds the line is flagged")

    def test_a_file_missing_the_line_fails_and_names_it(self):
        code, out = self.verdict("Work the brief.")
        self.assertEqual(code, 1, "a file with no terse line passed the check: %r" % out)
        self.assertEqual(len(out.splitlines()), 1, "one missing line gave a finding count other than one: %r" % out)
        self.assertTrue(names(out, os.path.basename(self.NAME)), "the finding does not name the file: %r" % out)

    def test_an_empty_file_fails(self):
        root = fixture_root()
        code, out = check_files(write(root, self.NAME, ""))
        self.assertEqual(code, 1, "an empty file passed the check: %r" % out)

    def test_a_full_size_file_with_the_line_at_the_end_passes(self):
        self.assertEqual(self.verdict(long_prose() + "\n\n" + TERSE_LINE), (0, ""),
                         "a long file with the line at its end is flagged")

    def test_a_line_wrapped_over_a_break_counts(self):
        self.assertEqual(self.verdict("Work the brief.\n\n" + wrapped(TERSE_LINE)), (0, ""),
                         "a line wrapped over a line break is flagged")

    def test_a_line_in_a_backtick_fence_does_not_count(self):
        self.assertEqual(self.verdict("```\n%s\n```" % TERSE_LINE)[0], 1,
                         "a line inside a ``` fence counts as holding the line")
        self.assertEqual(self.verdict(TERSE_LINE)[0], 0, "control: the same line outside a fence is flagged")

    def test_a_line_in_a_tilde_fence_does_not_count(self):
        self.assertEqual(self.verdict("~~~\n%s\n~~~" % TERSE_LINE)[0], 1,
                         "a line inside a ~~~ fence counts as holding the line")
        self.assertEqual(self.verdict(TERSE_LINE)[0], 0, "control: the same line outside a fence is flagged")

    def test_a_line_in_a_one_line_comment_does_not_count(self):
        self.assertEqual(self.verdict("<!-- %s -->" % TERSE_LINE)[0], 1,
                         "a line inside a one-line HTML comment counts as holding the line")
        self.assertEqual(self.verdict(TERSE_LINE)[0], 0, "control: the same line outside a comment is flagged")

    def test_a_line_in_a_multi_line_comment_does_not_count(self):
        self.assertEqual(self.verdict("<!--\n%s\n-->" % TERSE_LINE)[0], 1,
                         "a line inside a multi-line HTML comment counts as holding the line")
        self.assertEqual(self.verdict(TERSE_LINE)[0], 0, "control: the same line outside a comment is flagged")

    def test_a_comment_closed_before_the_line_leaves_the_line_counted(self):
        self.assertEqual(self.verdict("<!--\nA note.\n-->\n\n" + TERSE_LINE), (0, ""),
                         "the line after a closed comment is flagged")

    def test_a_comment_opener_in_inline_code_opens_no_comment(self):
        self.assertEqual(self.verdict("Write `<!--` to open a comment.\n\n" + TERSE_LINE), (0, ""),
                         "a comment opener in inline code hid the line")

    def test_a_comment_opener_across_a_wrapped_code_span_opens_no_comment(self):
        self.assertEqual(self.verdict("Write `a\n<!--` here.\n\n" + TERSE_LINE), (0, ""),
                         "a comment opener in a code span that wraps over a line break hid the line")

    def test_a_comment_opener_inside_a_fence_opens_no_comment(self):
        self.assertEqual(self.verdict("```\n<!--\n```\n\n" + TERSE_LINE), (0, ""),
                         "a comment opener inside a fence hid the line after the fence")

    def test_a_fence_marker_mid_line_opens_no_fence(self):
        self.assertEqual(self.verdict("Write ``` to open a fence.\n\n" + TERSE_LINE), (0, ""),
                         "a fence marker in the middle of a line hid the line")

    def test_a_fence_marker_inside_a_comment_opens_no_fence(self):
        self.assertEqual(self.verdict("<!--\n```\n-->\n\n" + TERSE_LINE), (0, ""),
                         "a fence marker inside an HTML comment opened a fence that hid the line after the comment")

    def test_a_line_inside_a_comment_with_a_fence_marker_does_not_count(self):
        self.assertEqual(self.verdict("<!--\n```\n%s\n-->" % TERSE_LINE)[0], 1,
                         "a line inside a comment that holds a fence marker counts as holding the line")

    def test_a_fence_closed_by_a_shorter_marker_stays_open(self):
        self.assertEqual(self.verdict("````\nAn example.\n```\n%s\n````" % TERSE_LINE)[0], 1,
                         "a three-backtick line closed a four-backtick fence, so the line after it counted")
        self.assertEqual(self.verdict("````\nAn example.\n````\n\n" + TERSE_LINE), (0, ""),
                         "control: a four-backtick fence closed by four backticks hid the line after it")

    def test_a_fence_closed_by_a_longer_marker_closes(self):
        self.assertEqual(self.verdict("```\nAn example.\n````\n\n" + TERSE_LINE), (0, ""),
                         "a four-backtick line did not close a three-backtick fence, so the line after it was hidden")

    def test_a_line_named_only_inside_a_code_span_does_not_count(self):
        self.assertEqual(self.verdict("Quote the rule `%s` here." % TERSE_LINE)[0], 1,
                         "a line inside a code span counts as holding the line")
        self.assertEqual(self.verdict("Quote the rule here.\n\n" + TERSE_LINE), (0, ""),
                         "control: the line outside a code span is flagged")

    def test_a_lone_quote_in_prose_hides_nothing(self):
        self.assertEqual(self.verdict("Don't stop early. Say \"no.\n\n" + TERSE_LINE), (0, ""),
                         "a lone quote in prose hid the line")

    def test_a_lone_backtick_does_not_pair_across_a_blank_line(self):
        # Controls first: the same text without the lone backtick counts, and a one-line span still hides its line.
        self.assertEqual(self.verdict("Don't skip this.\n\n" + TERSE_LINE + "\n\nUse `x` here."), (0, ""),
                         "control: the line after a quote and a one-line span was hidden")
        self.assertEqual(self.verdict("Quote `" + TERSE_LINE + "` here.")[0], 1,
                         "control: a one-line code span holding the line counted as holding it")
        self.assertEqual(self.verdict("Quote `" + wrapped(TERSE_LINE) + "` here.")[0], 1,
                         "control: a code span wrapped over one line break counted as holding its line")
        self.assertEqual(self.verdict("Don`t skip this.\n\n" + TERSE_LINE + "\n\nUse `x` here."), (0, ""),
                         "a lone backtick paired with a backtick across a blank line hid the line")

    def test_a_code_span_does_not_span_a_blank_line(self):
        # Controls first: a span closed in its paragraph hides nothing after it; a span over one line break still hides its line.
        self.assertEqual(self.verdict("Write `a\nb` here.\n\n" + TERSE_LINE), (0, ""),
                         "control: a code span closed in its paragraph hid the line after it")
        self.assertEqual(self.verdict("Write `a\n" + wrapped(TERSE_LINE) + "\nb` here.")[0], 1,
                         "control: a code span across one line break did not hide the line it holds")
        self.assertEqual(self.verdict("Write `a\n\n" + TERSE_LINE + "\n\nb` here."), (0, ""),
                         "a code span opened in one paragraph and closed in another hid the line between them")

    def test_a_four_space_indented_code_block_does_not_count(self):
        # Controls first: three spaces is a paragraph, and a list item's four-space continuation counts.
        self.assertEqual(self.verdict("Work the brief.\n\n   " + TERSE_LINE), (0, ""),
                         "control: a three-space paragraph holding the line was flagged")
        self.assertEqual(self.verdict("- Every lane keeps its prose short. "
                                      + wrapped(TERSE_LINE).replace("\n", "\n    ")), (0, ""),
                         "control: a list item's four-space continuation holding the line was flagged")
        self.assertEqual(self.verdict("Work the brief.\n\n    " + TERSE_LINE)[0], 1,
                         "a four-space indented code block holding the line counted as holding it")

    def test_a_four_space_line_under_a_paragraph_line_counts(self):
        # Control first: the same line unindented under the text line counts.
        self.assertEqual(self.verdict("Work the brief.\n" + TERSE_LINE), (0, ""),
                         "control: an unindented line under a text line was flagged")
        self.assertEqual(self.verdict("Work the brief.\n    " + TERSE_LINE), (0, ""),
                         "a four-space line continuing a paragraph was read as code, so the line did not count")

    def test_a_list_item_four_space_line_after_a_blank_line_counts(self):
        # Control first: the same line unindented after the blank line counts.
        self.assertEqual(self.verdict("- Every lane keeps its prose short.\n\n" + TERSE_LINE), (0, ""),
                         "control: an unindented line after a list item and a blank line was flagged")
        self.assertEqual(self.verdict("- Every lane keeps its prose short.\n\n    " + TERSE_LINE), (0, ""),
                         "a list item's four-space paragraph after a blank line was read as code, so the line did not count")

    # The reader is CommonMark. An inline comment opened mid-line ends at its paragraph break, so it cannot
    # hide a line below a blank line. A comment opened at a line start is a block: it hides the rest of the
    # line it closes on, and it ends with its list item.
    def test_an_unclosed_mid_line_comment_opener_hides_nothing_below_it_in_its_paragraph(self):
        # Controls first: a comment closed on its line, or closed in its paragraph, hides nothing after it.
        self.assertEqual(self.verdict("Work the brief. <!-- open --> stays.\n" + TERSE_LINE), (0, ""),
                         "control: the line after a mid-line comment closed on its line was hidden")
        self.assertEqual(self.verdict("Work the brief. <!-- open\nclose --> stays.\n\n" + TERSE_LINE), (0, ""),
                         "control: the line after a mid-line comment closed in its paragraph was hidden")
        self.assertEqual(self.verdict("Work the brief. <!-- open\n" + TERSE_LINE + "\n--> stays.")[0], 1,
                         "control: a line inside a mid-line comment closed in its paragraph counted as holding the line")
        self.assertEqual(self.verdict("Work the brief. <!-- open\n" + TERSE_LINE), (0, ""),
                         "an unclosed mid-line comment opener hid the terse line below it in the same paragraph")

    def test_an_unclosed_mid_line_comment_opener_hides_nothing_after_a_blank_line(self):
        self.assertEqual(self.verdict("Write <!-- open --> to open a comment.\n\n" + TERSE_LINE), (0, ""),
                         "control: the line after a mid-line comment closed on its line and a blank line was hidden")
        self.assertEqual(self.verdict("Write <!-- to open a comment.\n\n" + TERSE_LINE), (0, ""),
                         "an unclosed mid-line comment opener hid the terse line after a blank line")

    def test_an_unclosed_mid_line_comment_opener_hides_nothing_after_a_blank_line_in_a_full_size_file(self):
        self.assertEqual(self.verdict(long_prose() + "\n\nWrite <!-- open --> to open a comment.\n\n" + TERSE_LINE),
                         (0, ""), "control: a full-size file with a closed mid-line comment before the line was flagged")
        self.assertEqual(self.verdict(long_prose() + "\n\nWrite <!-- to open a comment.\n\n" + TERSE_LINE), (0, ""),
                         "an unclosed mid-line comment opener in a full-size file hid the terse line after a blank line")

    def test_a_mid_line_comment_does_not_close_in_a_later_paragraph(self):
        # Controls first: a comment closed inside its paragraph hides nothing after it, and a line it holds counts as hidden.
        self.assertEqual(self.verdict("Work <!-- note\nspans a break --> stays.\n\n" + TERSE_LINE), (0, ""),
                         "control: the line after a comment closed inside its paragraph was hidden")
        self.assertEqual(self.verdict("Work <!-- " + TERSE_LINE + "\nspans --> stays.")[0], 1,
                         "control: a line inside a mid-line comment that spans a break in its paragraph counted")
        self.assertEqual(self.verdict("Work the brief. <!-- open\n\n" + TERSE_LINE + "\n\n-->"), (0, ""),
                         "a mid-line comment opener closed in a later paragraph hid the terse line between them")

    def test_an_unclosed_mid_line_comment_opener_after_a_fence_hides_nothing_after_a_blank_line(self):
        self.assertEqual(self.verdict("```\ncode\n```\nWork the brief. <!-- open --> stays.\n\n" + TERSE_LINE),
                         (0, ""), "control: the line after a closed comment that follows a fence was hidden")
        self.assertEqual(self.verdict("```\ncode\n```\nWork the brief. <!-- open\n\n" + TERSE_LINE), (0, ""),
                         "an unclosed mid-line comment opener after a fence hid the terse line after a blank line")

    def test_an_unclosed_mid_line_comment_opener_after_indented_code_hides_nothing_after_a_blank_line(self):
        self.assertEqual(self.verdict("    code\nWork the brief. <!-- open --> stays.\n\n" + TERSE_LINE), (0, ""),
                         "control: the line after a closed comment that follows an indented code line was hidden")
        self.assertEqual(self.verdict("    code\nWork the brief. <!-- open\n\n" + TERSE_LINE), (0, ""),
                         "an unclosed mid-line comment opener after an indented code line hid the terse line after a blank line")

    def test_an_unclosed_mid_line_comment_opener_in_a_list_item_hides_nothing_after_a_blank_line(self):
        self.assertEqual(self.verdict("- Work the brief. <!-- open --> stays.\n\n" + TERSE_LINE), (0, ""),
                         "control: the line after a closed comment in a list item was hidden")
        self.assertEqual(self.verdict("- Work the brief. <!-- open\n\n" + TERSE_LINE), (0, ""),
                         "an unclosed mid-line comment opener in a list item hid the terse line after a blank line")

    def test_an_unclosed_mid_line_comment_opener_in_a_list_item_continuation_hides_nothing(self):
        self.assertEqual(self.verdict("- item\n\n  Work <!-- open --> stays.\n\n  " + TERSE_LINE), (0, ""),
                         "control: a list item's continuation after a closed comment was hidden")
        self.assertEqual(self.verdict("- item\n\n  Work <!-- open\n\n  " + TERSE_LINE), (0, ""),
                         "an unclosed mid-line comment opener in a list item's paragraph hid the item's next paragraph")

    def test_a_line_start_comment_in_a_list_item_ends_with_the_item(self):
        self.assertEqual(self.verdict("- item\n  <!-- open -->\n\n" + TERSE_LINE), (0, ""),
                         "control: the line after a line-start comment closed on its line in a list item was hidden")
        self.assertEqual(self.verdict("- item\n\n  <!-- open\n\n" + TERSE_LINE), (0, ""),
                         "a line-start comment in a list item hid the terse line after the list item ended")

    def test_a_line_start_comment_hides_the_text_after_its_close_on_the_same_line(self):
        # Controls first: text after a mid-line comment's close counts, and a line inside a mid-line comment is hidden.
        self.assertEqual(self.verdict("Work the brief. <!-- note --> " + TERSE_LINE), (0, ""),
                         "control: the text after a mid-line comment's close on the same line was hidden")
        self.assertEqual(self.verdict("Work the brief. <!-- " + TERSE_LINE + " -->")[0], 1,
                         "control: a line inside a mid-line comment counted as holding the line")
        self.assertEqual(self.verdict("<!-- note -->\n\n" + TERSE_LINE), (0, ""),
                         "control: the line after a line-start comment closed on its own line was hidden")
        self.assertEqual(self.verdict("<!-- note --> " + TERSE_LINE)[0], 1,
                         "the text after a line-start comment's close on the same line counted as holding the line")

    def test_a_line_start_comment_closed_on_a_later_line_hides_the_text_after_its_close(self):
        self.assertEqual(self.verdict("Work the brief. <!-- note\n--> " + TERSE_LINE), (0, ""),
                         "control: the text after an inline comment's close on a later line was hidden")
        self.assertEqual(self.verdict("<!-- note\n--> " + TERSE_LINE)[0], 1,
                         "the text after a line-start comment's close on a later line counted as holding the line")

    def test_a_line_start_comment_after_a_paragraph_line_hides_the_text_after_its_close(self):
        # Controls first: a line-start comment closed on its own line hides nothing below it, and one never closed hides the rest.
        self.assertEqual(self.verdict("Work the brief.\n<!-- note -->\n\n" + TERSE_LINE), (0, ""),
                         "control: the line after a line-start comment closed on its own line was hidden")
        self.assertEqual(self.verdict("Work the brief.\n<!-- open\n\n" + TERSE_LINE)[0], 1,
                         "control: an unclosed line-start comment after a paragraph line did not hide the rest of the file")
        self.assertEqual(self.verdict("Work the brief.\n<!-- note --> " + TERSE_LINE)[0], 1,
                         "the text after a line-start comment's close on the same line counted as holding the line")

    def test_a_line_start_comment_indented_one_to_three_spaces_hides_the_text_after_its_close(self):
        self.assertEqual(self.verdict("   <!-- note -->\n\n" + TERSE_LINE), (0, ""),
                         "control: the line after a 3-space line-start comment closed on its own line was hidden")
        self.assertEqual(self.verdict("   <!-- note --> " + TERSE_LINE)[0], 1,
                         "the text after a 3-space line-start comment's close on the same line counted as holding the line")

    def test_a_four_space_comment_after_text_is_not_a_block(self):
        # Control first: a three-space comment after text is a block that hides the rest of its line.
        self.assertEqual(self.verdict("Work the brief.\n   <!-- open --> " + TERSE_LINE)[0], 1,
                         "control: a three-space line-start comment after text did not hide the rest of its line")
        self.assertEqual(self.verdict("Work the brief.\n    <!-- open --> " + TERSE_LINE), (0, ""),
                         "a four-space comment that continues a paragraph was read as a block, so the text after its close was hidden")

    def test_an_unclosed_line_start_comment_in_a_list_item_ends_with_the_item(self):
        self.assertEqual(self.verdict("- item\n  <!-- open -->\n\n" + TERSE_LINE), (0, ""),
                         "control: the line after a line-start comment closed on its line in a list item was hidden")
        self.assertEqual(self.verdict("- item\n  <!-- open\n\n" + TERSE_LINE), (0, ""),
                         "an unclosed line-start comment in a list item hid the terse line after the list item ended")

    # A heading, a fence, a list item, a quote or a rule line interrupts a paragraph, so a comment opened mid-line
    # above one ends there. Each row has a control beside it: the same block after a comment closed on its line.
    def assert_block_ends_an_unclosed_comment(self, block, name):
        self.assertEqual(self.verdict("Write <!-- open --> to open.\n" + block + "\n" + TERSE_LINE), (0, ""),
                         "control: the line after a closed comment and a %s was hidden" % name)
        self.assertEqual(self.verdict("Write <!-- open\n" + block + "\n" + TERSE_LINE + "\n-->")[0], 0,
                         "a comment opened above a %s ran past it, so the line below it was hidden" % name)

    def test_a_heading_ends_an_unclosed_mid_line_comment(self):
        # Control first: the comment ends with its paragraph, so a heading and a blank line leave the line below counted.
        self.assertEqual(self.verdict("Write <!-- open\n## Heading\n\n" + TERSE_LINE), (0, ""),
                         "control: the line after an unclosed comment, a heading and a blank line was hidden")
        self.assert_block_ends_an_unclosed_comment("## Heading", "heading")

    def test_a_list_item_ends_an_unclosed_mid_line_comment(self):
        self.assert_block_ends_an_unclosed_comment("- item", "list item")

    def test_a_quote_ends_an_unclosed_mid_line_comment(self):
        self.assert_block_ends_an_unclosed_comment("> quote", "quote")

    def test_a_rule_ends_an_unclosed_mid_line_comment(self):
        self.assert_block_ends_an_unclosed_comment("***", "rule line")

    def test_a_nested_list_item_ends_an_unclosed_mid_line_comment(self):
        self.assertEqual(self.verdict("- a\n  Write <!-- open -->\n  - b\n" + TERSE_LINE), (0, ""),
                         "control: the line after a closed comment in a nested item was hidden")
        self.assertEqual(self.verdict("- a\n  Write <!-- open\n  - b\n" + TERSE_LINE + "\n-->")[0], 0,
                         "a comment opened above a nested item ran into it, so the line below it was hidden")

    def test_a_fence_ends_an_unclosed_mid_line_comment(self):
        self.assertEqual(self.verdict("Write <!-- x -->\n```\n" + TERSE_LINE + "\n```")[0], 1,
                         "control: a line in a fence after a closed comment counted as holding the line")
        self.assertEqual(self.verdict("Write <!-- x\n```\n-->\n" + TERSE_LINE + "\n```")[0], 1,
                         "a comment opened above a fence ran into it, so a line inside the fence counted")

    def test_a_fence_after_an_unclosed_mid_line_comment_does_not_hide_the_text_after_it(self):
        self.assertEqual(self.verdict("```\n-->\n```\n\n" + TERSE_LINE), (0, ""),
                         "control: a fence holding --> hid the line after it")
        self.assertEqual(self.verdict("Write <!-- x\n```\n-->\n```\n\n" + TERSE_LINE), (0, ""),
                         "a comment opened above a fence ran past the fence's first line, so the text after the fence was hidden")

    def test_an_ordered_item_ends_an_unclosed_mid_line_comment(self):
        self.assert_block_ends_an_unclosed_comment("1. item", "ordered list item")

    def test_a_plus_item_ends_an_unclosed_mid_line_comment(self):
        self.assert_block_ends_an_unclosed_comment("+ item", "plus list item")

    def test_a_star_item_ends_an_unclosed_mid_line_comment(self):
        self.assert_block_ends_an_unclosed_comment("* item", "star list item")

    def test_a_dash_rule_ends_an_unclosed_mid_line_comment(self):
        self.assert_block_ends_an_unclosed_comment("---", "dash rule line")

    def test_an_underscore_rule_ends_an_unclosed_mid_line_comment(self):
        self.assert_block_ends_an_unclosed_comment("___", "underscore rule line")

    def test_a_tilde_fence_ends_an_unclosed_mid_line_comment(self):
        # Control first: a line in a ~~~ fence after a closed comment is fenced, so it does not count.
        self.assertEqual(self.verdict("Write <!-- x -->\n~~~\n" + TERSE_LINE + "\n~~~")[0], 1,
                         "control: a line in a ~~~ fence after a closed comment counted as holding the line")
        self.assertEqual(self.verdict("Write <!-- x\n~~~\n-->\n~~~\n\n" + TERSE_LINE), (0, ""),
                         "a comment opened above a ~~~ fence ran past the fence's first line, so the text after the fence was hidden")

    def test_a_line_start_comment_ends_the_paragraph_above_it(self):
        # Control first: a comment closed on its line leaves the line above a line-start comment counted.
        self.assertEqual(self.verdict("Write <!-- open --> to open.\n" + TERSE_LINE + "\n<!-- c -->"), (0, ""),
                         "control: the line above a line-start comment, after a closed comment, was hidden")
        self.assertEqual(self.verdict("Write <!-- open\n" + TERSE_LINE + "\n<!-- c -->"), (0, ""),
                         "a line-start comment did not end the paragraph above it, so an unclosed mid-line comment hid the line above it")

    def assert_rule_clears_the_list(self, rule, name):
        # Control first: a closed comment below the rule hides nothing. A rule is not an item, so the item's list ends.
        self.assertEqual(self.verdict("- a\n" + rule + "\n  <!-- open -->\n" + TERSE_LINE), (0, ""),
                         "control: the line after a closed comment below a %s was hidden" % name)
        self.assertEqual(self.verdict("- a\n" + rule + "\n  <!-- open\n" + TERSE_LINE)[0], 1,
                         "a %s did not clear the list above it, so an unclosed comment below it ended with the item and the line after it counted" % name)

    def test_a_dash_rule_clears_the_list(self):
        self.assert_rule_clears_the_list("---", "dash rule line")

    def test_a_spaced_star_rule_clears_the_list(self):
        self.assert_rule_clears_the_list("* * *", "spaced star rule line")

    def test_a_spaced_dash_rule_clears_the_list(self):
        self.assert_rule_clears_the_list("- - -", "spaced dash rule line")

    # The list ends at a column-0 heading or fence. An indented comment after one is top-level, not in the list.
    def test_a_column_zero_heading_ends_the_list_before_an_indented_comment(self):
        self.assertEqual(self.verdict("- item\n# Heading\n  <!-- open -->\n\n" + TERSE_LINE), (0, ""),
                         "control: the line after a closed comment below a heading was hidden")
        self.assertEqual(self.verdict("- item\n# Heading\n  <!-- open\n\n" + TERSE_LINE)[0], 1,
                         "a list still open after a column-0 heading ended an unclosed comment early, so the line after it counted")

    def test_a_column_zero_fence_ends_the_list_before_an_indented_comment(self):
        self.assertEqual(self.verdict("- item\n```\ncode\n```\n  <!-- open -->\n\n" + TERSE_LINE), (0, ""),
                         "control: the line after a closed comment below a fence was hidden")
        self.assertEqual(self.verdict("- item\n```\ncode\n```\n  <!-- open\n\n" + TERSE_LINE)[0], 1,
                         "a list still open after a column-0 fence ended an unclosed comment early, so the line after it counted")

    def test_the_outer_item_width_returns_after_a_nested_item(self):
        self.assertEqual(self.verdict("- a\n  - b\n\n  <!-- open -->\n\n" + TERSE_LINE), (0, ""),
                         "control: the line after a closed comment under the outer item was hidden")
        self.assertEqual(self.verdict("- a\n  - b\n\n  <!-- open\n\n" + TERSE_LINE)[0], 0,
                         "after a nested item the outer item's width was not restored, so an unclosed comment hid the line below the list")

    def test_an_ordered_item_holds_its_unclosed_comment_in_its_item(self):
        # Control first: a closed comment hides nothing. The content column of "1. " is 3, so the comment is indented 3.
        self.assertEqual(self.verdict("1. item\n\n   <!-- open -->\n\n" + TERSE_LINE), (0, ""),
                         "control: the line after a closed comment under an ordered item was hidden")
        self.assertEqual(self.verdict("1. item\n\n   <!-- open\n\n" + TERSE_LINE), (0, ""),
                         "an ordered item did not hold its unclosed comment, so the line after the item was hidden")

    def test_a_plus_item_holds_its_unclosed_comment_in_its_item(self):
        self.assertEqual(self.verdict("+ item\n\n  <!-- open -->\n\n" + TERSE_LINE), (0, ""),
                         "control: the line after a closed comment under a plus item was hidden")
        self.assertEqual(self.verdict("+ item\n\n  <!-- open\n\n" + TERSE_LINE), (0, ""),
                         "a plus item did not hold its unclosed comment, so the line after the item was hidden")

    def test_a_five_space_item_gap_puts_its_content_at_the_marker_plus_one(self):
        # Controls first: a closed comment hides nothing, and a four-space gap sets the content column at 5, so a
        # two-space comment is outside that item and hides the text below it.
        self.assertEqual(self.verdict("-     item\n\n  <!-- open -->\n\n" + TERSE_LINE), (0, ""),
                         "control: the line after a closed comment under a five-space item was hidden")
        self.assertEqual(self.verdict("-    item\n\n  <!-- open\n\n" + TERSE_LINE)[0], 1,
                         "control: a four-space item gap did not put its content at column 5, so the comment was read as inside")
        self.assertEqual(self.verdict("-     item\n\n  <!-- open\n\n" + TERSE_LINE), (0, ""),
                         "a five-space item gap did not put its content at column 2, so the comment was read as outside the item and hid the line after it")

    def test_a_line_at_the_item_column_stays_in_an_unclosed_comment_of_the_item(self):
        # Control first: a line indented less than the item's column ends its comment, so the line below it counts.
        self.assertEqual(self.verdict("- item\n  <!-- open\n " + TERSE_LINE + "\n  -->"), (0, ""),
                         "control: a line indented less than the item's column did not end its unclosed comment")
        self.assertEqual(self.verdict("- item\n  <!-- open\n  " + TERSE_LINE + "\n  -->")[0], 1,
                         "a line at the item's column ended its unclosed comment, so the line counted")

    def test_an_outer_indent_line_closes_the_nested_item(self):
        # Controls first: a closed comment hides nothing below it, and a line at the outer indent inside an unclosed
        # comment stays hidden. That comment sits in the outer item, after the nested item has ended.
        self.assertEqual(self.verdict("- a\n  - b\n  <!-- open -->\n" + TERSE_LINE), (0, ""),
                         "control: the line after a closed comment under a nested item was hidden")
        self.assertEqual(self.verdict("- a\n  - b\n  <!-- open\n  " + TERSE_LINE + "\n  -->")[0], 1,
                         "control: a line at the outer indent inside an unclosed comment counted as holding the line")
        self.assertEqual(self.verdict("- a\n  - b\n  <!-- open\ntext " + TERSE_LINE), (0, ""),
                         "a line at the outer indent did not close the nested item, so an unclosed comment hid the text after it")

    def test_a_file_that_cannot_be_read_is_unknown_not_clear(self):
        root = fixture_root()
        path = os.path.join(root, self.NAME)
        os.makedirs(path)  # a folder where the file should be: open() fails on it for every reader
        code, out = check_files(path)
        self.assertNotIn(code, (0, 1), "an unreadable file exited %r, which reads as clear or broken: %r" % (code, out))
        self.assertIn("unknown", out.lower(), "the finding for an unreadable file does not say unknown: %r" % out)
        self.assertTrue(names(out, os.path.basename(path)), "the finding for an unreadable file does not name it: %r" % out)


class RoleFileBody(BodyCases, unittest.TestCase):
    NAME = os.path.join("agents", "builder.md")

    # The frontmatter cases hold for agents/*.md only: the lane text has no frontmatter.
    def test_a_line_only_in_frontmatter_does_not_count(self):
        # Controls first: the same line in the body after the closing --- counts.
        self.assertEqual(self.verdict("Work the brief.\n\n" + TERSE_LINE,
                                      front="name: fixture\ndescription: Work the brief."), (0, ""),
                         "control: the line in the body after the frontmatter was flagged")
        self.assertEqual(self.verdict("Work the brief.", front="name: fixture\ndescription: " + TERSE_LINE)[0], 1,
                         "a line only in the frontmatter counted as holding the line")

    def test_a_line_only_in_frontmatter_of_an_empty_body_does_not_count(self):
        self.assertEqual(self.verdict("", front="name: fixture\ndescription: Work the brief.")[0], 1,
                         "control: an empty body with no line passed")
        self.assertEqual(self.verdict("", front="name: fixture\ndescription: " + TERSE_LINE)[0], 1,
                         "a line only in the frontmatter of an empty body counted as holding the line")

    def test_a_line_only_in_frontmatter_of_a_full_size_file_does_not_count(self):
        self.assertEqual(self.verdict(long_prose() + "\n\n" + TERSE_LINE, front="name: fixture"), (0, ""),
                         "control: a full-size file with the line in its body was flagged")
        self.assertEqual(self.verdict(long_prose(), front="name: fixture\ndescription: " + TERSE_LINE)[0], 1,
                         "a full-size file with the line only in its frontmatter counted as holding the line")

    def test_a_file_with_no_frontmatter_is_read_whole(self):
        self.assertEqual(self.verdict(TERSE_LINE, front=None), (0, ""),
                         "a file with no frontmatter was not read whole: the line was missed")
        self.assertEqual(self.verdict("Intro.\n\n---\n\n" + TERSE_LINE + "\n\n---", front=None), (0, ""),
                         "a --- rule that is not on line 1 was read as frontmatter and hid the line")

    def test_a_line_before_a_rule_off_line_one_counts(self):
        # Control first: the same text with no rule counts.
        self.assertEqual(self.verdict(TERSE_LINE + "\n\nsome text\n\nIntro.", front=None), (0, ""),
                         "control: a line before plain text with no rule was flagged")
        self.assertEqual(self.verdict(TERSE_LINE + "\n\nsome text\n\n---\n\nIntro.", front=None), (0, ""),
                         "a --- rule that is not on line 1 was read as frontmatter and hid the line before it")


class LaneTextBody(BodyCases, unittest.TestCase):
    NAME = LANE_TEXT


class ScannerCases(unittest.TestCase):
    """body_text on raw text. A file read turns CRLF into LF, so only the scanner itself sees a CRLF line end."""

    def test_a_crlf_blank_line_ends_a_comment_opened_above_it(self):
        self.assertIn(TERSE_LINE, C.body_text("Write <!-- open\n\n" + TERSE_LINE + "\n-->"),
                      "control: the line after an LF blank line was hidden")
        self.assertIn(TERSE_LINE, C.body_text("Write <!-- open\r\n\r\n" + TERSE_LINE + "\r\n-->"),
                      "a CRLF blank line did not end a comment opened above it, so the line below it was hidden")


class CountingText(str):
    """A str that counts the characters its find and slice calls scan. A regex search is not counted,
    since its work is inside the engine."""
    scanned = 0

    def find(self, sub, *bounds):
        found = str.find(self, sub, *bounds)
        start = bounds[0] if bounds else 0
        stop = found if found >= 0 else (bounds[1] if len(bounds) > 1 else len(self))
        self.scanned += max(0, min(stop, len(self)) - start)
        return found

    def __getitem__(self, key):
        part = str.__getitem__(self, key)
        self.scanned += len(part) if isinstance(key, slice) else 1
        return part


class CountingSearch:
    """Stands in for SPAN_OR_COMMENT in body_text. Counts its search calls, then runs the real pattern."""

    def __init__(self, pattern):
        self.pattern = pattern
        self.calls = 0

    def search(self, text, pos=0):
        self.calls += 1
        return self.pattern.search(text, pos)


class ScanCost(unittest.TestCase):
    """The scan's cost grows no faster than its input, and an unclosed paragraph is not searched for comments.
    Both are counted, not timed (test-strategy-reset, point 2): the list case counts the characters that body_text's
    find and slice calls scan, and the paragraph case counts its searches."""
    NAME = os.path.join("agents", "builder.md")
    SMALL = 500  # the repeats of a shape in the paragraph case and the control
    COUNT_SMALL = 250  # the counted list has this many repeats, then twice as many
    COUNT_LIMIT = 2.5  # a linear scan doubles its count on a doubled input; a quadratic one nearly quadruples it

    def work(self, body):
        """The characters body_text's finds and slices scan on body."""
        text = CountingText(body)
        C.body_text(text)
        return text.scanned

    def searches(self, body):
        """How many times body_text searches body for a comment or a code span."""
        counting = CountingSearch(C.SPAN_OR_COMMENT)
        with mock.patch.object(C, "SPAN_OR_COMMENT", counting):
            C.body_text(body)
        return counting.calls

    def test_an_unclosed_paragraph_of_openers_is_never_searched(self):
        # Control first: a closed comment is searched for, so a count of 0 below means the scan skipped the paragraph.
        self.assertGreaterEqual(self.searches("x <!-- y --> z"), 1,
                                "control: a closed comment was not searched for, so the counter sees nothing")
        self.assertEqual(self.searches("x <!-- " * self.SMALL + "\n\n" + TERSE_LINE), 0,
                         "a paragraph of unclosed openers with no --> was searched for comments")

    def test_a_long_list_of_line_start_comments_scans_no_more_than_linear(self):
        small_body = "- item\n" + "  <!-- x -->\n" * self.COUNT_SMALL + "\n" + TERSE_LINE
        big_body = "- item\n" + "  <!-- x -->\n" * (2 * self.COUNT_SMALL) + "\n" + TERSE_LINE
        small, big = self.work(small_body), self.work(big_body)
        # Control first: the counter saw at least the characters of the input, so a count of 0 cannot pass.
        self.assertGreaterEqual(small, len(small_body),
                                "the counter saw fewer characters than the input holds, so the ratio proves nothing")
        self.assertLessEqual(big, self.COUNT_LIMIT * small,
                             "a list of line-start comments twice as long scanned %d characters against %d: "
                             "the scan is worse than linear" % (big, small))

    def test_a_paragraph_with_one_lone_backtick_is_never_searched(self):
        # Control first: a paragraph with a closed code span is searched, so a count of 0 below means the scan skipped it.
        self.assertGreaterEqual(self.searches("word <!-- x\n" * self.SMALL + "`a`\n\n" + TERSE_LINE), 1,
                                "control: a paragraph with a closed code span was not searched, so the counter sees nothing")
        self.assertEqual(self.searches("word <!-- x\n" * self.SMALL + "`\n\n" + TERSE_LINE), 0,
                         "a paragraph of unclosed openers with one lone backtick was searched for comments and code spans")

    def test_a_paragraph_with_one_lone_backtick_scans_no_more_than_linear(self):
        # The regex search's own steps are not counted here; the search count above covers them.
        small_body = "word <!-- x\n" * self.COUNT_SMALL + "`\n\n" + TERSE_LINE
        big_body = "word <!-- x\n" * (2 * self.COUNT_SMALL) + "`\n\n" + TERSE_LINE
        small, big = self.work(small_body), self.work(big_body)
        # Control first: the counter saw at least the characters of the input, so a count of 0 cannot pass.
        self.assertGreaterEqual(small, len(small_body),
                                "the counter saw fewer characters than the input holds, so the ratio proves nothing")
        self.assertLessEqual(big, self.COUNT_LIMIT * small,
                             "a paragraph with one lone backtick twice as long scanned %d characters against %d: "
                             "the scan is worse than linear" % (big, small))

    def test_both_long_shapes_still_count_the_line_after_them(self):
        paragraph = write(fixture_root(), self.NAME, doc("x <!-- " * self.SMALL + "\n\n" + TERSE_LINE))
        self.assertEqual(check_files(paragraph), (0, ""),
                         "a long paragraph of unclosed openers hid the line after it")
        listed = write(fixture_root(), self.NAME, doc("- item\n" + "  <!-- x -->\n" * self.SMALL + "\n" + TERSE_LINE))
        self.assertEqual(check_files(listed), (0, ""),
                         "a long list of line-start comments hid the line after the list")


def make_tree(root, missing=(), bare=(), lane_bare=False):
    """A fixture repository: a role file per name with the line, except the missing ones and the bare ones."""
    for name in ROLES:
        if name in missing:
            continue
        body = "Work the brief." if name in bare else "Work the brief.\n\n" + TERSE_LINE
        write(root, os.path.join("agents", name + ".md"), doc(body))
    lane = "Start the lane." if lane_bare else "Start the lane.\n\n" + TERSE_LINE
    write(root, LANE_TEXT, doc(lane))
    return root


def run_tree(root):
    with mock.patch.object(C, "ROOT", root):
        return check_files()


class NoArgumentRun(unittest.TestCase):
    def test_a_clean_fixture_tree_passes(self):
        self.assertEqual(run_tree(make_tree(fixture_root())), (0, ""), "a clean fixture tree is flagged")

    def test_a_role_file_missing_the_line_fails_and_names_it(self):
        code, out = run_tree(make_tree(fixture_root(), bare=("builder",)))
        self.assertEqual(code, 1, "a role file with no line passed the no-argument run: %r" % out)
        self.assertTrue(names(out, "builder.md"), "the finding does not name builder.md: %r" % out)
        self.assertEqual(len(out.splitlines()), 1, "one bare role file gave more than one finding: %r" % out)

    def test_the_lane_text_missing_the_line_fails_and_names_it(self):
        code, out = run_tree(make_tree(fixture_root(), lane_bare=True))
        self.assertEqual(code, 1, "the lane text with no line passed the no-argument run: %r" % out)
        self.assertTrue(names(out, "operating-model.md"), "the finding does not name the lane text: %r" % out)

    def test_a_named_role_with_no_file_fails(self):
        code, out = run_tree(make_tree(fixture_root(), missing=("reviewer",)))
        self.assertEqual(code, 1, "a named role with no file passed the no-argument run: %r" % out)
        self.assertTrue(names(out, "reviewer.md"), "the finding does not name reviewer.md: %r" % out)

    def test_an_agent_file_outside_the_ten_is_checked_too(self):
        root = make_tree(fixture_root())
        write(root, os.path.join("agents", "extra.md"), doc("Work the brief."))
        code, out = run_tree(root)
        self.assertEqual(code, 1, "an agents/*.md file with no line passed: %r" % out)
        self.assertTrue(names(out, "extra.md"), "the finding does not name extra.md: %r" % out)


class MixedRun(unittest.TestCase):
    def test_a_missing_line_and_an_unreadable_file_exit_1_and_name_both(self):
        root = make_tree(fixture_root(), bare=("builder",))
        unreadable = os.path.join(root, "agents", "designer.md")
        os.remove(unreadable)
        os.makedirs(unreadable)  # a folder where the file should be: open() fails on it for every reader
        code, out = run_tree(root)
        self.assertEqual(code, 1, "a run with a missing line and an unreadable file exited %r, not 1: %r" % (code, out))
        self.assertTrue(names(out, "builder.md"), "the missing line is not named: %r" % out)
        self.assertTrue(names(out, "designer.md"), "the unreadable file is not named: %r" % out)
        self.assertIn("unknown", " ".join(names(out, "designer.md")).lower(),
                      "the unreadable file is not reported as unknown: %r" % out)
        self.assertEqual(len(out.splitlines()), 2, "the mixed run gave a finding count other than two: %r" % out)


class RealTree(unittest.TestCase):
    def test_the_ten_named_role_files_are_in_agents(self):
        present = set(os.listdir(os.path.join(ROOT, "agents")))
        for name in ROLES:
            self.assertIn(name + ".md", present, "agents/%s.md is missing" % name)

    def test_every_real_role_file_holds_the_line(self):
        folder = os.path.join(ROOT, "agents")
        found = sorted(name for name in os.listdir(folder) if name.endswith(".md"))
        self.assertTrue(found, "agents/ holds no agent file to check")
        for name in found:
            with self.subTest(agent=name):
                code, out = check_files(os.path.join(folder, name))
                self.assertEqual(code, 0, "agents/%s fails the check: %r" % (name, out))

    def test_the_real_lane_text_holds_the_line(self):
        code, out = check_files(os.path.join(ROOT, LANE_TEXT))
        self.assertEqual(code, 0, "%s fails the check: %r" % (LANE_TEXT, out))

    def test_the_real_tree_passes_the_no_argument_run(self):
        self.assertEqual(check_files(), (0, ""), "the real tree fails the no-argument run")


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
