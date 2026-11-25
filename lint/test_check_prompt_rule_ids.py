#!/usr/bin/env python3
"""Cases for lint/check_prompt_rule_ids.py: a rule id a model prompt names needs an anchor.

    python3 lint/test_check_prompt_rule_ids.py

The lint reads hooks/*.py with ast and collects the rule ids that the named prompt constants
name. It fails on each id with no `<!-- rule:<id> -->` anchor in a RULE_FILES file
(lint/rule_audit.py), and its message names the file, the line and the id. The reader API these
cases call:

    prompt_ids(root) -> [(path, line, id), ...]   each id a prompt names, as read; path is "hooks/<file>.py"
    problems(root)   -> [message, ...]            one message per unanchored id

Each case builds a fixture tree in the run folder (lint/_test_temp.py). A negative case carries a
positive control beside it, a dead id that must be flagged, so "not flagged" cannot pass on a reader
that saw nothing. The real-tree cases read this repo.
"""
import importlib
import os
import re
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
import rule_audit  # noqa: E402  the anchor files the lint shares with the anchor reader (lint/rule_audit.py)

RUN_FOLDER = None  # made in setUpModule, so an import leaks no folder


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


def lint():
    """The lint module, loaded when a case calls it. Until it is built, each case fails on this assert, not on an import error."""
    if not os.path.isfile(os.path.join(HERE, "check_prompt_rule_ids.py")):
        raise AssertionError("lint/check_prompt_rule_ids.py is not built")
    return importlib.import_module("check_prompt_rule_ids")


CLAUDE_MD = (
    "# Rules\n\n"
    "**Output.** Write plainly.<!-- rule:output-write-in-ste -->\n"
    "**Verify.** Count from REST.<!-- rule:verification-counts-from-rest -->\n"
)
STYLE_PATH = os.path.join("output-styles", "shiv-stylisms.md")
OUTPUT_STYLE = (
    "# Style\n\n"
    "- Cut narration and recaps.<!-- rule:style-cut-narration -->\n"
)


def make_tree(hooks=None, claude_md=CLAUDE_MD, extra=None):
    """A fixture repo in a fresh folder under the run folder. `hooks` maps a hooks/ file name to its source."""
    files = {"CLAUDE.md": claude_md, STYLE_PATH: OUTPUT_STYLE}
    assert set(files) == set(rule_audit.RULE_FILES), "scope: the fixture's anchor files are not rule_audit.RULE_FILES"
    for name, src in (hooks or {}).items():
        files[os.path.join("hooks", name)] = src
    files.update(extra or {})
    root = tempfile.mkdtemp(dir=RUN_FOLDER)
    for rel, text in files.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    return root


def judged(*ids):
    """A reply_judge.py-shaped source: JUDGED_RULES on line 1, one id per line after it."""
    return "JUDGED_RULES = (\n" + "".join('    "%s",\n' % i for i in ids) + ")\n"


def line_of(src, text):
    """The 1-based line of `src` that holds `text`. Asserts the text is there, so a moved fixture fails here."""
    for n, line in enumerate(src.splitlines(), 1):
        if text in line:
            return n
    raise AssertionError("scope: %r is not in the fixture source" % text)


def names_place(message, path, line):
    """True when `message` names `path`, then `line`, with only non-digits between them."""
    return re.search(re.escape(path) + r"\D{0,12}?" + str(line) + r"(?!\d)", message) is not None


class AnchoredIdTests(unittest.TestCase):
    """An id with an anchor in a RULE_FILES file passes."""

    def test_id_anchored_in_the_output_style_passes(self):
        src = judged("style-cut-narration")
        root = make_tree(hooks={"reply_judge.py": src})
        self.assertIn(("hooks/reply_judge.py", line_of(src, "style-cut-narration"), "style-cut-narration"),
                      lint().prompt_ids(root))
        self.assertEqual(lint().problems(root), [])

    def test_id_anchored_in_claude_md_passes(self):
        src = judged("output-write-in-ste")
        root = make_tree(hooks={"reply_judge.py": src})
        self.assertIn(("hooks/reply_judge.py", line_of(src, "output-write-in-ste"), "output-write-in-ste"),
                      lint().prompt_ids(root))
        self.assertEqual(lint().problems(root), [])


class UnanchoredIdTests(unittest.TestCase):
    """An id with no anchor fails, and the message names its file, line and id."""

    def test_id_with_no_anchor_fails_and_names_file_line_and_id(self):
        src = judged("output-write-in-ste", "output-made-up-id")
        problems = lint().problems(make_tree(hooks={"reply_judge.py": src}))
        self.assertEqual(len(problems), 1, problems)
        self.assertTrue(names_place(problems[0], "hooks/reply_judge.py", line_of(src, "output-made-up-id")), problems[0])
        self.assertIn("output-made-up-id", problems[0])
        self.assertNotIn("output-write-in-ste", problems[0], "a message names one cause")

    def test_each_unanchored_id_gets_its_own_message(self):
        src = judged("output-ghost-one", "output-ghost-two")
        problems = lint().problems(make_tree(hooks={"reply_judge.py": src}))
        self.assertEqual(len(problems), 2, problems)
        for ghost in ("output-ghost-one", "output-ghost-two"):
            hits = [m for m in problems if ghost in m]
            self.assertEqual(len(hits), 1, problems)
            self.assertTrue(names_place(hits[0], "hooks/reply_judge.py", line_of(src, ghost)), hits[0])

    def test_tuple_item_without_a_family_prefix_is_flagged(self):
        # A JUDGED_RULES item is an id as written, whatever its prefix; the real dead id is one.
        src = judged("measure-before-priority")
        problems = lint().problems(make_tree(hooks={"reply_judge.py": src}))
        self.assertEqual(len(problems), 1, problems)
        self.assertTrue(names_place(problems[0], "hooks/reply_judge.py", line_of(src, "measure-before-priority")), problems[0])
        self.assertIn("measure-before-priority", problems[0])

    def test_an_anchor_outside_the_rule_files_does_not_count(self):
        src = judged("output-ghost-elsewhere")
        extra = {os.path.join("docs", "rules.md"): "- Rule.<!-- rule:output-ghost-elsewhere -->\n"}
        problems = lint().problems(make_tree(hooks={"reply_judge.py": src}, extra=extra))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("output-ghost-elsewhere", problems[0])


class PromptScanTests(unittest.TestCase):
    """What the reader counts as an id inside a prompt, and what it leaves alone."""

    def test_ordinary_hyphenated_words_are_not_ids(self):
        # Control: output-ghost-real is an id (a family word) and must be read; the others are not.
        src = ('INSTRUCTIONS = (\n'
               '    "Run red-run first, and never owner-override a guard. "\n'
               '    "Cite the decision test-practices, and a tokens-made-up-thing word. "\n'
               '    "Flag output-ghost-real in a reply."\n'
               ')\n')
        root = make_tree(hooks={"reply_judge.py": src})
        self.assertEqual(lint().prompt_ids(root),
                         [("hooks/reply_judge.py", line_of(src, "output-ghost-real"), "output-ghost-real")])

    def test_comment_and_docstring_ids_are_not_flagged(self):
        # Control: the id in JUDGED_RULES is read; the comment, the docstrings and NOTE (not a prompt constant) are not.
        src = ('"""Module note: output-ghost-doc is prose."""\n'
               '# output-ghost-comment: a comment, not a prompt.\n'
               'NOTE = "output-ghost-note"\n'
               'def helper():\n'
               '    """Docstring naming output-ghost-fn."""\n'
               '    return 1\n'
               'JUDGED_RULES = ("output-ghost-real",)\n')
        root = make_tree(hooks={"reply_judge.py": src})
        self.assertEqual(lint().prompt_ids(root),
                         [("hooks/reply_judge.py", line_of(src, "output-ghost-real"), "output-ghost-real")])
        self.assertEqual(len(lint().problems(root)), 1)

    def test_a_comment_opener_inside_a_string_does_not_hide_what_follows(self):
        # `#`, `//` and `/*` sit inside the string; the lone quote in "Don't" must not end the scan early.
        src = ('INSTRUCTIONS = (\n'
               '    "Use # for headings, // for paths and /* for blocks. "\n'
               '    "Don\'t hide output-ghost-after-openers: the rule."\n'
               ')\n')
        root = make_tree(hooks={"reply_judge.py": src})
        self.assertEqual(lint().prompt_ids(root),
                         [("hooks/reply_judge.py", line_of(src, "output-ghost-after-openers"), "output-ghost-after-openers")])

    def test_a_multi_line_string_is_read_whole(self):
        src = ('INSTRUCTIONS = """Judge the reply.\n'
               'Line two has no id.\n'
               'output-ghost-deep: the rule on line three.\n'
               '"""\n')
        root = make_tree(hooks={"reply_judge.py": src})
        self.assertEqual(lint().prompt_ids(root),
                         [("hooks/reply_judge.py", line_of(src, "output-ghost-deep"), "output-ghost-deep")])

    def test_implicit_concatenation_reports_the_physical_line(self):
        src = ('INSTRUCTIONS = ("first part. "\n'
               '                "second part. "\n'
               '                "output-ghost-concat: third part.")\n')
        root = make_tree(hooks={"reply_judge.py": src})
        self.assertEqual(lint().prompt_ids(root),
                         [("hooks/reply_judge.py", line_of(src, "output-ghost-concat"), "output-ghost-concat")])

    def test_a_part_that_instructions_is_built_from_is_read(self):
        src = ('GH_PART = "output-ghost-part: a part of the judge text."\n'
               'INSTRUCTIONS = "Judge the reply. " + GH_PART + " End."\n')
        root = make_tree(hooks={"reply_judge.py": src})
        self.assertEqual(lint().prompt_ids(root),
                         [("hooks/reply_judge.py", line_of(src, "output-ghost-part"), "output-ghost-part")])

    def test_every_named_prompt_constant_is_read(self):
        spawn = 'SPAWN_PROMPT = (\n    "output-ghost-spawn: text.",\n)\n'
        wording = 'WORDING_PROMPT = "output-ghost-wording: text %s"\n'
        prose = 'COMMON = "output-ghost-common: text."\nRULES = {\n    "ok": "output-ghost-rules: text.",\n}\n'
        root = make_tree(hooks={"call_judge.py": spawn, "sendmessage_state.py": wording, "prose_judge.py": prose})
        expected = [
            ("hooks/call_judge.py", line_of(spawn, "output-ghost-spawn"), "output-ghost-spawn"),
            ("hooks/sendmessage_state.py", line_of(wording, "output-ghost-wording"), "output-ghost-wording"),
            ("hooks/prose_judge.py", line_of(prose, "output-ghost-common"), "output-ghost-common"),
            ("hooks/prose_judge.py", line_of(prose, "output-ghost-rules"), "output-ghost-rules"),
        ]
        self.assertEqual(sorted(lint().prompt_ids(root)), sorted(expected))

    def test_only_hooks_files_are_read(self):
        root = make_tree(hooks={"reply_judge.py": judged("output-ghost-hook")},
                         extra={os.path.join("lint", "helper.py"): judged("output-ghost-lint")})
        self.assertEqual(lint().prompt_ids(root),
                         [("hooks/reply_judge.py", 2, "output-ghost-hook")])


class SizeTests(unittest.TestCase):
    """The empty state and the full-size state."""

    def test_a_tree_with_no_prompt_constant_names_no_id(self):
        root = make_tree(hooks={"guard.py": "LIMIT = 3\n"})
        self.assertEqual(lint().prompt_ids(root), [])
        self.assertEqual(lint().problems(root), [])

    def test_a_full_size_tree_of_anchored_ids_passes(self):
        names = ["output-full-%03d" % n for n in range(200)]
        claude = CLAUDE_MD + "".join("**Rule.** Text.<!-- rule:%s -->\n" % n for n in names)
        root = make_tree(hooks={"reply_judge.py": judged(*names)}, claude_md=claude)
        self.assertEqual(len(lint().prompt_ids(root)), 200)
        self.assertEqual(lint().problems(root), [])


class RealTreeTests(unittest.TestCase):
    """This repo's own tree."""

    def test_real_tree_reads_the_judged_rules_ids(self):
        # Scope: the reader sees JUDGED_RULES on the real tree, so the case below is not a pass over an empty read.
        found = {i for p, _, i in lint().prompt_ids(ROOT) if p == "hooks/reply_judge.py"}
        self.assertIn("output-start-with-point", found)

    def test_real_tree_no_longer_names_measure_before_priority(self):
        # Red until the builder fixes measure-before-priority in hooks/reply_judge.py (no anchor; its home is style-measure-before-priority); green after that fix.
        named = [m for m in lint().problems(ROOT) if re.search(r"(?<![\w-])measure-before-priority(?![\w-])", m)]
        self.assertEqual(named, [])


if __name__ == "__main__":
    unittest.main()
