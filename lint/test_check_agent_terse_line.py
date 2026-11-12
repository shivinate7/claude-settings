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
line start hides the rest of the line it closes on. The line may wrap over a line break.
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

    def test_an_unclosed_line_start_comment_in_a_list_item_ends_with_the_item(self):
        self.assertEqual(self.verdict("- item\n  <!-- open -->\n\n" + TERSE_LINE), (0, ""),
                         "control: the line after a line-start comment closed on its line in a list item was hidden")
        self.assertEqual(self.verdict("- item\n  <!-- open\n\n" + TERSE_LINE), (0, ""),
                         "an unclosed line-start comment in a list item hid the terse line after the list item ended")

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
