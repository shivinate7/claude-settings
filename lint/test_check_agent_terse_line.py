#!/usr/bin/env python3
"""Fixture suite for lint/check_agent_terse_line.py. Run: python3 lint/test_check_agent_terse_line.py

Each agent role file (the ten named roles, and any other agents/*.md) and the lane start text
(skills/project-ops/templates/operating-model.md) must hold TERSE_LINE, the one short-output line the
check exports. The line counts as body text only. A line inside a code fence (``` or ~~~) or inside an
HTML comment does not count. A comment opener or a fence marker inside inline code or in the middle of a
line opens nothing, and a lone quote in prose hides nothing. The line may wrap over a line break.
A file that cannot be read is unknown (exit 2, named), never clear.

The no-argument run reads the module's ROOT when it runs. These cases patch ROOT to a fixture tree.
"""
import contextlib, io, os, shutil, sys, tempfile, time, unittest, uuid
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import check_agent_terse_line as C  # noqa: E402  the check and the one home of TERSE_LINE
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (the one home, lint/_test_temp.py)
RUN_FOLDER = _test_temp.run_folder()

TERSE_LINE = C.TERSE_LINE
# The ten role files the brief names. A deleted one is a finding, so the list is pinned here, not read from agents/.
ROLES = ("builder", "claude-code-guide", "design-reviewer", "designer", "explore",
         "plan", "record-writer", "refuter", "reviewer", "test-author")
LANE_TEXT = os.path.join("skills", "project-ops", "templates", "operating-model.md")


def doc(body):
    """A file with frontmatter, then the body. The frontmatter holds no line the check reads."""
    return "---\nname: fixture\n---\n# Fixture\n\n%s\n" % body


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

    def verdict(self, body):
        root = fixture_root()
        return check_files(write(root, self.NAME, doc(body)))

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
        prose = "\n".join("Prose line %d of the file." % n for n in range(3000))
        self.assertEqual(self.verdict(prose + "\n\n" + TERSE_LINE), (0, ""),
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

    def test_a_lone_quote_in_prose_hides_nothing(self):
        self.assertEqual(self.verdict("Don't stop early. Say \"no.\n\n" + TERSE_LINE), (0, ""),
                         "a lone quote in prose hid the line")

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


class RunFolder(unittest.TestCase):
    def test_first_request_sweeps_old_siblings_and_keeps_new_ones(self):
        # test-temp-standard: the first request of a run removes a sibling over a day old and keeps a newer one.
        root = os.path.join(RUN_FOLDER, "sweep")
        old = os.path.join(root, "1-%s" % uuid.uuid4().hex)
        new = os.path.join(root, "2-%s" % uuid.uuid4().hex)
        for path in (old, new):
            os.makedirs(path)
        two_days_ago = time.time() - 2 * 24 * 60 * 60
        os.utime(old, (two_days_ago, two_days_ago))
        own = _test_temp.run_folder(temp_root=root)
        self.assertFalse(os.path.exists(old), "an old sibling run folder survived the sweep")
        self.assertTrue(os.path.isdir(new), "a new sibling run folder was swept")
        self.assertTrue(os.path.isdir(own))


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
