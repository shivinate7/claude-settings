#!/usr/bin/env python3
"""Fixture tests for rule_audit.py.

Each test builds a small CLAUDE.md fragment, a map, and (when it matters) a guard.py or
checks.yml fragment in memory, then calls `check(...)` directly. No subprocess: the audit
itself does not touch the transcript or the hook protocol the way report_guard does.

Run with:

    python3 lint/test_rule_audit.py -v
"""
import ast
import glob
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rule_audit  # noqa: E402
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
import test_rule_homes  # noqa: E402  the files a rule anchor may sit in (lint/test_rule_homes.py)

# .mjs fixtures must be listable: form 1 names node:test, form 2 names LIST_TESTS (see rule_audit).
NODE_TEST = 'import { test } from "node:test";\n'


def list_tests_form(body):
    return ('const tests = [];\nconst test = (name, fn) => tests.push({ name, fn });\n' + body
            + 'if (process.env.LIST_TESTS === "1") { for (const { name } of tests) console.log("LISTED " + JSON.stringify(name)); process.exit(0); }\n')

GUARD_SRC = '''
def dispatch():
    refuse(tool, "deny", "shared-tree", REASON, matched)
    refuse(tool, "ask", "agent-model-cap", REASON, matched)
    record(tool, "noted", "merge-main", matched)
'''

WORKFLOW_SRC = '''
jobs:
  checks:
    steps:
      - name: Guard fixture suite
        run: python3 hooks/test_guard.py
'''

GOOD_MD = (
    "**Shared trees.** Never run `git stash` in a shared checkout."
    "<!-- rule:shared-trees-no-destructive-git -->\n"
)
GOOD_MAP = {
    "rules": {
        "shared-trees-no-destructive-git": {
            "mechanism": {"kind": "guard", "ref": "shared-tree"}
        }
    }
}


def kind_count(rule_map, kind):
    rules = rule_map.get("rules", {})
    return sum(1 for r in rules.values()
               if isinstance(r, dict) and (r.get("mechanism") or {}).get("kind") == kind)


def run(md=GOOD_MD, rule_map=None, guard=GUARD_SRC, workflow=WORKFLOW_SRC,
        rule_floor=1, unmechanized_expected=None, judgment_expected=None):
    """Call check() with small pins sized to the fixture, not this repo's real numbers."""
    if rule_map is None:
        rule_map = GOOD_MAP
    if unmechanized_expected is None:
        unmechanized_expected = kind_count(rule_map, "unmechanized")
    if judgment_expected is None:
        judgment_expected = kind_count(rule_map, "judgment")
    return rule_audit.check(md, rule_map, guard, workflow, rule_floor, unmechanized_expected,
                            judgment_expected=judgment_expected)


def check_map(mechanism):
    mechanism = dict(mechanism, kind="check")
    return {"rules": {"shared-trees-no-destructive-git": {"mechanism": mechanism}}}


class RuleFileTree:
    """Mixin for a TestCase. `rule_tree` writes the named files under a run folder and reads them back through
    rule_text(). Every RULE_FILES entry is written, empty when the case names none, so the reader never meets a
    missing file, whatever the list holds."""

    def rule_tree(self, files):
        root = _test_temp.run_folder()
        self.addCleanup(shutil.rmtree, root, True)
        for rel in sorted(set(files) | {p.replace(os.sep, "/") for p in rule_audit.RULE_FILES}):
            path = os.path.join(root, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(files.get(rel, ""))
        return rule_audit.rule_text(root)


class RuleAuditTests(RuleFileTree, unittest.TestCase):

    def test_single_mapped_rule_is_clean(self):
        problems = run()
        self.assertEqual(problems, [])

    def test_new_rule_with_no_row_fails_and_names_it(self):
        md = GOOD_MD + "**New.** Never skip the review.<!-- rule:new-never-skip-review -->\n"
        problems = run(md=md)
        self.assertTrue(any("new-never-skip-review" in p and "no row" in p for p in problems),
                         problems)

    def test_row_naming_a_dead_guard_rule_fails_as_stale(self):
        rule_map = {
            "rules": {
                "shared-trees-no-destructive-git": {
                    "mechanism": {"kind": "guard", "ref": "does-not-exist"}
                }
            }
        }
        problems = run(rule_map=rule_map)
        self.assertTrue(any("does-not-exist" in p and "Stale row" in p for p in problems),
                         problems)

    def test_row_naming_a_real_guard_rule_passes(self):
        rule_map = {
            "rules": {
                "shared-trees-no-destructive-git": {
                    "mechanism": {"kind": "guard", "ref": "agent-model-cap"}
                }
            }
        }
        problems = run(rule_map=rule_map)
        self.assertEqual(problems, [])

    def test_row_naming_a_missing_check_file_fails(self):
        rule_map = {
            "rules": {
                "shared-trees-no-destructive-git": {
                    "mechanism": {"kind": "check", "ref": "lint/does_not_exist.py"}
                }
            }
        }
        problems = run(rule_map=rule_map)
        self.assertTrue(any("does_not_exist.py" in p for p in problems), problems)

    def test_row_citing_a_needle_is_refused(self):
        # The old shape: a real file and a substring that is present. It must go red now.
        rule_map = check_map({"ref": "lint/rule_audit.py", "needle": "every rule anchor maps"})
        problems = run(rule_map=rule_map)
        self.assertTrue(any("needle" in p for p in problems), problems)

    def test_check_row_with_no_test_and_no_setting_is_refused(self):
        problems = run(rule_map=check_map({"ref": "lint/rule_audit.py"}))
        self.assertTrue(any("proves nothing" in p for p in problems), problems)

    def test_check_row_citing_a_real_test_passes(self):
        problems = run(rule_map=check_map({
            "ref": "lint/rule_audit.py",
            "test": "lint/test_rule_audit.py::RuleAuditTests.test_single_mapped_rule_is_clean"}))
        self.assertEqual(problems, [])

    def test_check_row_citing_a_test_that_does_not_exist_fails(self):
        problems = run(rule_map=check_map({
            "ref": "lint/rule_audit.py",
            "test": "lint/test_rule_audit.py::RuleAuditTests.test_no_such_thing"}))
        self.assertTrue(any("does not resolve" in p for p in problems), problems)

    def test_check_row_citing_a_docstring_phrase_as_a_test_fails(self):
        problems = run(rule_map=check_map({
            "ref": "hooks/test_guard.py",
            "test": "hooks/test_guard.py::drives the guard as Claude Code drives it"}))
        self.assertTrue(any("does not resolve" in p for p in problems), problems)

    def test_check_row_with_a_setting_that_holds_passes(self):
        problems = run(rule_map=check_map({
            "ref": "settings.json",
            "setting": {"file": "settings.json", "path": "env.CLAUDE_CODE_SUBAGENT_MODEL",
                        "equals": "sonnet"}}))
        self.assertEqual(problems, [])

    def test_check_row_with_a_wrong_setting_value_fails(self):
        # The name is present in settings.json; only the value is wrong.
        problems = run(rule_map=check_map({
            "ref": "settings.json",
            "setting": {"file": "settings.json", "path": "env.CLAUDE_CODE_SUBAGENT_MODEL",
                        "equals": "opus"}}))
        self.assertTrue(any("does not hold" in p for p in problems), problems)

    def test_check_row_with_a_setting_name_absent_fails(self):
        problems = run(rule_map=check_map({
            "ref": "settings.json",
            "setting": {"file": "settings.json", "path": "env.NO_SUCH_NAME", "equals": "1"}}))
        self.assertTrue(any("does not hold" in p for p in problems), problems)

    def test_row_naming_a_dead_ci_step_fails(self):
        rule_map = {
            "rules": {
                "shared-trees-no-destructive-git": {
                    "mechanism": {"kind": "ci", "ref": "Step that does not exist"}
                }
            }
        }
        problems = run(rule_map=rule_map)
        self.assertTrue(any("Step that does not exist" in p for p in problems), problems)

    def test_row_naming_a_real_ci_step_passes(self):
        rule_map = {
            "rules": {
                "shared-trees-no-destructive-git": {
                    "mechanism": {"kind": "ci", "ref": "Guard fixture suite"}
                }
            }
        }
        problems = run(rule_map=rule_map)
        self.assertEqual(problems, [])

    def test_unmechanized_with_a_thin_reason_fails(self):
        rule_map = {
            "rules": {
                "shared-trees-no-destructive-git": {
                    "mechanism": {"kind": "unmechanized", "reason": "no reason"}
                }
            }
        }
        problems = run(rule_map=rule_map)
        self.assertTrue(any("rubber stamp" in p for p in problems), problems)

    def test_orphaned_row_with_no_anchor_left_fails(self):
        rule_map = {
            "rules": {
                "shared-trees-no-destructive-git": {
                    "mechanism": {"kind": "guard", "ref": "shared-tree"}
                },
                "a-deleted-rule": {
                    "mechanism": {
                        "kind": "unmechanized",
                        "reason": "This rule was removed from CLAUDE.md but its row was left behind by mistake.",
                    }
                },
            }
        }
        problems = run(rule_map=rule_map)
        self.assertTrue(any("a-deleted-rule" in p and "no rule anchor" in p for p in problems),
                         problems)

    def test_floor_catches_a_shrunk_reader(self):
        problems = run(rule_floor=5)
        self.assertTrue(any("fewer than the pinned floor" in p for p in problems), problems)

    def test_unmechanized_pin_catches_a_silent_drop(self):
        rule_map = {
            "rules": {
                "shared-trees-no-destructive-git": {
                    "mechanism": {
                        "kind": "unmechanized",
                        "reason": "Nothing enforces this yet, written out at enough length.",
                    }
                }
            }
        }
        problems = run(rule_map=rule_map, unmechanized_expected=0)
        self.assertTrue(any("more than the pinned 0" in p for p in problems), problems)

    def _rule_files(self, claude_md, style_md):
        """CLAUDE.md and the output style, read back through rule_text()."""
        return self.rule_tree({"CLAUDE.md": claude_md, "output-styles/shiv-stylisms.md": style_md})

    def test_anchor_only_in_the_style_file_is_read(self):
        style = "- Lead with the result.<!-- rule:style-only-rule -->\n"
        rules = dict(GOOD_MAP["rules"])
        rules["style-only-rule"] = {"mechanism": {
            "kind": "unmechanized",
            "reason": "No check reads whether the first sentence of a reply gives the result.",
        }}
        problems = run(md=self._rule_files(GOOD_MD, style), rule_map={"rules": rules},
                       rule_floor=2)
        self.assertEqual(problems, [])

    def test_duplicate_anchor_split_across_claude_md_and_style_fails(self):
        style = GOOD_MD
        problems = run(md=self._rule_files(GOOD_MD, style))
        self.assertTrue(any("duplicate" in p and "shared-trees-no-destructive-git" in p
                            for p in problems), problems)

JUDGMENT_REASON = "No check can judge whether this sentence was followed, so a person must."
TWO_RULE_MD = GOOD_MD + "**Second.** Judge it.<!-- rule:second-judged-rule -->\n"


def one_row_map(kind, reason=None):
    mechanism = {"kind": kind}
    if reason is not None:
        mechanism["reason"] = reason
    return {"rules": {"shared-trees-no-destructive-git": {"mechanism": mechanism}}}


class JudgmentKindTests(unittest.TestCase):
    """`judgment`: an unmechanized rule whose reason says no check can judge it. Same reason
    floor as `unmechanized`, its own pin JUDGMENT_EXPECTED, passed as `judgment_expected`.
    `unmechanized` never reads `ref`, so no ref case is pinned."""

    def reason_problems(self, problems):
        # Only a reason check says these words. "unknown mechanism kind 'judgment'" does not.
        return [p for p in problems
                if "judgment" in p and ("words of reason" in p or "rubber stamp" in p)]

    def test_judgment_is_a_kind_with_its_own_integer_pin(self):
        self.assertIn("judgment", rule_audit.KINDS)
        self.assertIsInstance(rule_audit.JUDGMENT_EXPECTED, int)

    def test_judgment_row_with_a_full_reason_is_clean(self):
        problems = run(rule_map=one_row_map("judgment", JUDGMENT_REASON), judgment_expected=1)
        self.assertEqual(problems, [])

    def test_judgment_reason_of_exactly_the_minimum_words_is_clean(self):
        reason = " ".join(["word"] * rule_audit.REASON_MIN_WORDS)
        problems = run(rule_map=one_row_map("judgment", reason), judgment_expected=1)
        self.assertEqual(problems, [])

    def test_judgment_reason_one_word_short_fails_as_a_reason_problem(self):
        reason = " ".join(["word"] * (rule_audit.REASON_MIN_WORDS - 1))
        problems = run(rule_map=one_row_map("judgment", reason), judgment_expected=1)
        self.assertTrue(self.reason_problems(problems), problems)

    def test_judgment_with_a_thin_empty_blank_or_missing_reason_fails(self):
        for reason in ("no reason", "", "   ", None):
            with self.subTest(reason=reason):
                problems = run(rule_map=one_row_map("judgment", reason), judgment_expected=1)
                self.assertTrue(self.reason_problems(problems), problems)

    def test_judgment_count_above_the_pin_fails_as_more(self):
        problems = run(rule_map=one_row_map("judgment", JUDGMENT_REASON), judgment_expected=0)
        self.assertTrue(any("judgment" in p and "more than the pinned 0" in p for p in problems),
                        problems)

    def test_judgment_count_below_the_pin_fails_as_fewer(self):
        # A `>` in place of `!=` passes the case above and misses this one. GOOD_MAP has no judgment row.
        problems = run(judgment_expected=1)
        self.assertTrue(any("judgment" in p and "fewer than the pinned 1" in p for p in problems),
                        problems)

    def test_judgment_row_is_not_counted_as_unmechanized(self):
        # One judgment row, unmechanized pin 0: clean only if that pin counts `unmechanized` alone.
        problems = run(rule_map=one_row_map("judgment", JUDGMENT_REASON),
                       unmechanized_expected=0, judgment_expected=1)
        self.assertEqual(problems, [])

    def test_unmechanized_pin_ignores_judgment_rows_beside_unmechanized_ones(self):
        rule_map = {"rules": {
            "shared-trees-no-destructive-git": {"mechanism": {
                "kind": "unmechanized", "reason": JUDGMENT_REASON}},
            "second-judged-rule": {"mechanism": {"kind": "judgment", "reason": JUDGMENT_REASON}}}}
        problems = run(md=TWO_RULE_MD, rule_map=rule_map, unmechanized_expected=1,
                       judgment_expected=1)
        self.assertEqual(problems, [])

    def test_relabeling_unmechanized_as_judgment_cannot_dodge_the_pins(self):
        # The row was `unmechanized` (pin 1). Relabeled `judgment`, with neither pin moved.
        problems = run(rule_map=one_row_map("judgment", JUDGMENT_REASON),
                       unmechanized_expected=1, judgment_expected=0)
        self.assertTrue(any("unmechanized" in p and "fewer than the pinned 1" in p
                            for p in problems), problems)
        self.assertTrue(any("judgment" in p and "more than the pinned 0" in p
                            for p in problems), problems)


SIBLING_MAP = {
    "rules": {
        "shared-trees-no-destructive-git": {"mechanism": {"kind": "guard", "ref": "sibling-rule"}}
    }
}


class KindDocTests(unittest.TestCase):
    """The module docstring keeps the two kinds apart: only `judgment` says no check can judge the rule.
    A reader of `unmechanized` must not read it as the same case (claude-md-shrink)."""

    def bullet(self, kind):
        doc = rule_audit.__doc__
        start = doc.index("  - `%s`:" % kind)
        end = doc.find("\n  - `", start + 1)
        return doc[start:end if end != -1 else len(doc)]

    def test_unmechanized_bullet_does_not_say_cannot_be_checked(self):
        self.assertNotIn("cannot be checked", self.bullet("unmechanized"))

    def test_the_bullet_slice_reads_the_whole_unmechanized_bullet(self):
        # Control: a slice that came back short would pass the case above for the wrong reason.
        self.assertIn("reason", self.bullet("unmechanized"))


class GuardTextTests(unittest.TestCase):
    """`guard_text(root)` reads every hooks/guard*.py under root. A rule refused in a sibling
    module (guard_x.py, not guard.py) must resolve, and test files must not count as rule homes."""

    def tree(self, files):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, True)
        for rel, body in files.items():
            path = os.path.join(root, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(body)
        return root

    def files(self):
        refuse = 'refuse(tool, "deny", "%s", REASON, matched)\n'
        return {
            os.path.join("hooks", "guard.py"): refuse % "main-rule",
            os.path.join("hooks", "guard_x.py"): refuse % "sibling-rule",
            os.path.join("hooks", "test_guard.py"): refuse % "test-only-rule",
        }

    def test_rule_refused_only_in_a_sibling_module_resolves(self):
        root = self.tree(self.files())
        guard_text = rule_audit.guard_text(root)
        problems = rule_audit.check(GOOD_MD, SIBLING_MAP, guard_text, "", 1, 0, judgment_expected=0)
        self.assertEqual(problems, [])

    def test_guard_py_alone_leaves_that_sibling_rule_stale(self):
        """Control: the same fixture read the old way (guard.py only) must read red, so the
        case above proves the reader, not the fixture."""
        root = self.tree(self.files())
        guard_text = rule_audit.read(os.path.join(root, "hooks", "guard.py"))
        problems = rule_audit.check(GOOD_MD, SIBLING_MAP, guard_text, "", 1, 0, judgment_expected=0)
        self.assertTrue(any("sibling-rule" in p and "Stale row" in p for p in problems), problems)

    def test_guard_text_joins_guard_modules_and_no_test_file(self):
        root = self.tree(self.files())
        guard_text = rule_audit.guard_text(root)
        self.assertIn("main-rule", guard_text)
        self.assertIn("sibling-rule", guard_text)
        self.assertNotIn("test-only-rule", guard_text)


class SectionFileCitation(unittest.TestCase):
    """A test id on hooks/test_guard.py may name a case that a section file of the suite defines. The section
    files are tests/guard/*.py, read from the runner's SECTION_DIR, so the runner file alone does not hold it."""

    RUNNER_LINES = ('import os\n'
                    'HERE = os.path.dirname(os.path.abspath(__file__))\n'
                    'SECTION_DIR = os.path.join(HERE, "..", "tests", "guard")\n')
    CASE = "kill: a case that only a section file defines"

    def test_case_defined_only_in_a_section_file_resolves(self):
        run_dir = _test_temp.run_folder()
        try:
            os.makedirs(os.path.join(run_dir, "hooks"))
            os.makedirs(os.path.join(run_dir, "tests", "guard"))
            with open(os.path.join(run_dir, "hooks", "test_guard.py"), "w", encoding="utf-8") as f:
                f.write(self.RUNNER_LINES)
            with open(os.path.join(run_dir, "tests", "guard", "s00001-kill.py"), "w", encoding="utf-8") as f:
                f.write('# section 1\nsh("%s", "kill 1", "allow")\n' % self.CASE)
            with open(os.path.join(run_dir, "hooks", "test_guard.py"), encoding="utf-8") as f:
                self.assertNotIn(self.CASE, f.read(), "the scope: the runner file must not define the case itself")
            problem = rule_audit.citation_problem("hooks/test_guard.py::" + self.CASE, run_dir)
            self.assertIsNone(problem, "a case in a section file does not resolve: %s" % problem)
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)


class CitationTests(unittest.TestCase):
    """`citation_problem` over a throwaway tree: each known-bad file shape must read red."""

    def problem(self, src, test_id, filename="test_x.py"):
        with tempfile.TemporaryDirectory() as root:
            with open(os.path.join(root, filename), "w", encoding="utf-8") as f:
                f.write(src)
            return rule_audit.citation_problem(f"{filename}::{test_id}", root)

    def test_unittest_method_resolves(self):
        src = "import unittest\nclass T(unittest.TestCase):\n    def test_a(self): pass\n"
        self.assertIsNone(self.problem(src, "T.test_a"))
        self.assertIsNone(self.problem(src, "test_a"))

    def test_missing_name_is_red(self):
        src = "import unittest\nclass T(unittest.TestCase):\n    def test_a(self): pass\n"
        self.assertIn("no test", self.problem(src, "T.test_b"))

    def test_name_in_a_docstring_only_is_red(self):
        src = '"""test_a drives the guard."""\n'
        self.assertIn("no test", self.problem(src, "test_a"))

    def test_method_a_runner_never_collects_is_red(self):
        src = "class T:\n    def helper(self): pass\n"
        self.assertIn("not a test method", self.problem(src, "T.helper"))

    def test_duplicate_def_in_a_class_is_red(self):
        src = ("import unittest\nclass T(unittest.TestCase):\n"
               "    def test_a(self): pass\n    def test_a(self): assert False\n")
        self.assertIn("2 times", self.problem(src, "T.test_a"))

    def test_function_never_referenced_is_red(self):
        self.assertIn("never named", self.problem("def case_a(): pass\n", "case_a"))

    def test_function_referenced_by_a_runner_resolves(self):
        src = "def case_a(): pass\nCHECKS = (case_a,)\n"
        self.assertIsNone(self.problem(src, "case_a"))

    def test_registered_case_resolves_and_a_commented_one_is_red(self):
        self.assertIsNone(self.problem('sh("a case name", "ls", "allow")\n', "a case name"))
        self.assertIn("no test", self.problem('# sh("a case name", "ls", "allow")\n', "a case name"))

    def test_mjs_registration_resolves_and_a_comment_is_red(self):
        self.assertIsNone(self.problem(NODE_TEST + 'test("it works", () => {});\n', "it works", "t.mjs"))
        self.assertIn("registers no test", self.problem(NODE_TEST + '// test("it works", () => {});\n',
                                                        "it works", "t.mjs"))

    def test_mjs_non_ascii_name_is_listed_not_a_decode_crash(self):
        # Windows: node writes UTF-8, subprocess text=True decoded it as cp1252. The reader thread
        # died on byte 0x9D (the last byte of U+201D), stdout came back None, and citation_problem
        # raised AttributeError. A non-ASCII name must resolve to itself, with no crash and no mojibake.
        name = "café “quoted”"
        self.assertIsNone(self.problem(NODE_TEST + 'test("' + name + '", () => {});\n', name, "t.mjs"))

    def test_skipped_method_is_red(self):
        src = ("import unittest\nclass T(unittest.TestCase):\n"
               "    @unittest.skip('later')\n    def test_a(self): pass\n")
        self.assertIn("skip marker", self.problem(src, "T.test_a"))

    def test_method_that_skips_itself_is_red(self):
        src = ("import unittest\nclass T(unittest.TestCase):\n"
               "    def test_a(self):\n        self.skipTest('no')\n")
        self.assertIn("skip marker", self.problem(src, "T.test_a"))

    def test_method_in_a_skipped_class_is_red(self):
        src = ("import unittest\n@unittest.skip('x')\nclass T(unittest.TestCase):\n"
               "    def test_a(self): pass\n")
        self.assertIn("skip marker", self.problem(src, "T.test_a"))

    def test_test_method_in_a_plain_class_is_red(self):
        src = "class T:\n    def test_a(self): pass\n"
        self.assertIn("not a test method", self.problem(src, "T.test_a"))

    def test_method_in_a_class_deriving_a_local_testcase_resolves(self):
        src = ("import unittest\nclass B(unittest.TestCase): pass\n"
               "class T(B):\n    def test_a(self): pass\n")
        self.assertIsNone(self.problem(src, "T.test_a"))

    def test_case_function_named_only_under_if_false_is_red(self):
        src = "def case_a(): pass\nif False:\n    CHECKS = (case_a,)\n"
        self.assertIn("never named", self.problem(src, "case_a"))

    def test_case_function_named_only_by_an_uncalled_function_is_red(self):
        src = "def case_a(): pass\ndef dead():\n    return (case_a,)\n"
        self.assertIn("never named", self.problem(src, "case_a"))

    def test_case_function_named_by_a_called_function_resolves(self):
        src = "def case_a(): pass\ndef main():\n    case_a()\nmain()\n"
        self.assertIsNone(self.problem(src, "case_a"))

    def test_registration_inside_an_uncalled_function_is_red(self):
        src = 'def dead():\n    add("a case", 1)\n'
        self.assertIn("no test", self.problem(src, "a case"))

    def test_registration_inside_a_called_function_resolves(self):
        src = 'def build():\n    add("a case", 1)\nbuild()\n'
        self.assertIsNone(self.problem(src, "a case"))

    def test_mjs_scanner_reads_only_live_registrations(self):
        # Rows: each distinct .mjs source and its verdict. "registers no test" = the name is not live
        # (commented out, quoted, bare output, or a newline-split name). None = the name resolves.
        # Named failure: the scanner reads a commented-out .mjs test as live.
        red = "registers no test"
        cases = [
            ("block comment hides a registration", NODE_TEST + '/*\ntest("it works", () => {});\n*/\n',
             "it works", red),
            ("template literal hides a registration", NODE_TEST + 'const s = `\ntest("it works", () => {});\n`;\n',
             "it works", red),
            ("block comment with a note still registers", NODE_TEST + '/* note */\ntest("it works", () => {});\n',
             "it works", None),
            ("comment marker in a double-quoted string", NODE_TEST + 'const a = "image/*";\ntest("it works", () => {});\nconst b = "*/";\n',
             "it works", None),
            ("comment marker in a single-quoted string", NODE_TEST + "const a = 'image/*';\ntest(\"it works\", () => {});\nconst b = '*/';\n",
             "it works", None),
            ("url in a string", NODE_TEST + 'const u = "http://x";\ntest("it works", () => {});\n',
             "it works", None),
            ("regex quote hides a commented registration", list_tests_form("const re = /'/;\n/* don't\ntest(\"commented\", () => {});\n*/\n"),
             "commented", red),
            ("escaped slashes in a regex, line comment", list_tests_form('const re = /a\\/\\/b/;\n// test("commented", () => {});\n'),
             "commented", red),
            ("escaped slashes in a regex, block comment", list_tests_form('const re = /a\\/\\/b/;\n/*\ntest("commented", () => {});\n*/\n'),
             "commented", red),
            ("regex quote before a real registration", NODE_TEST + 'const re = /"/;\ntest("it works", () => {});\n',
             "it works", None),
            ("registration in a loop", NODE_TEST + 'for (let i = 0; i < 2; i++) {\n  test("it works", () => {});\n}\n',
             "it works", None),
            ("division then a quote in a comment", NODE_TEST + "const total = 6;\nconst half = total / 2 / 3;\n/* don't\ntest(\"commented\", () => {});\n*/\n",
             "commented", red),
            ("bare console.log of the name", NODE_TEST + 'console.log("it works");\n',
             "it works", red),
            ("bare console.log, form two", list_tests_form('console.log("it works");\n'),
             "it works", red),
            ("name with a newline", NODE_TEST + 'test("a\\nb", () => {});\n', "a", red),
            ("name with a newline, form two", list_tests_form('test("a\\nb", () => {});\n'), "a", red),
        ]
        for case, src, name, want in cases:
            with self.subTest(case):
                got = self.problem(src, name, "t.mjs")
                if want is None:
                    self.assertIsNone(got)
                else:
                    self.assertIn(want, got or "<None>")

    def test_mjs_without_node_on_path_says_names_could_not_be_read(self):
        with tempfile.TemporaryDirectory() as empty_path:
            with mock.patch.dict(os.environ, {"PATH": empty_path}):
                problem = self.problem(NODE_TEST + 'test("it works", () => {});\n', "it works", "t.mjs")
        self.assertIsNotNone(problem)
        self.assertIn("could not be read", problem)

    def test_mjs_form_two_registration_resolves(self):
        self.assertIsNone(self.problem(
            list_tests_form('test("it works", () => {});\n'), "it works", "t.mjs"))

    def test_mjs_nonzero_exit_says_names_could_not_be_read(self):
        problem = self.problem(NODE_TEST + 'test("it works", () => {});\nthrow new Error("boom");\n',
                               "it works", "t.mjs")
        self.assertIsNotNone(problem)
        self.assertIn("could not be read", problem)

    def test_mjs_top_level_busy_loop_says_names_could_not_be_read(self):
        with mock.patch.object(rule_audit, "NODE_LIST_TIMEOUT", 1):
            problem = self.problem(NODE_TEST + 'test("it works", () => {});\nwhile (true) {}\n',
                                   "it works", "t.mjs")
        self.assertIsNotNone(problem)
        self.assertIn("could not be read", problem)

    def test_mjs_with_no_known_way_to_list_is_refused(self):
        self.assertIn("no known way to list its tests", self.problem(
            'test("it works", () => {});\n', "it works", "t.mjs") or "<None>")

    def test_test_file_that_never_touches_the_ref_is_red(self):
        with tempfile.TemporaryDirectory() as root:
            for rel, body in (("check.py", "x = 1\n"), ("test_other.py", "import os\n"),
                              ("test_check.py", "import check\n"),
                              ("test_run.py", "import subprocess\nsubprocess.run(['python3', 'lint/check.py'])\n"),
                              ("test_mention.py", "NOTE = 'lint/check.py'\n")):
                with open(os.path.join(root, rel), "w", encoding="utf-8") as f:
                    f.write(body)
            self.assertIn("proves nothing",
                          rule_audit.link_problem("test_other.py::t", "lint/check.py", root))
            self.assertIsNone(rule_audit.link_problem("test_check.py::t", "lint/check.py", root))
            self.assertIsNone(rule_audit.link_problem("test_run.py::t", "lint/check.py", root))
            self.assertIn("proves nothing",
                          rule_audit.link_problem("test_mention.py::t", "lint/check.py", root))
            self.assertIsNone(rule_audit.link_problem("check.py::t", "check.py", root))

    def test_row_whose_test_never_touches_its_ref_fails(self):
        problems = run(rule_map=check_map({
            "ref": "lint/check_red_run.py",
            "test": "lint/test_rule_audit.py::RuleAuditTests.test_single_mapped_rule_is_clean"}))
        self.assertTrue(any("unlinked" in p for p in problems), problems)

    def test_missing_file_is_red(self):
        self.assertIn("does not exist",
                      rule_audit.citation_problem("nope.py::x", tempfile.gettempdir()))


# The ids hooks/guard.py writes that the old regex reader (a call with the rule third and a plain
# name first) never saw: ask_command() ids, a record() after a call, and the two tables.
GUARD_IDS_THE_REGEX_MISSED = (
    "force-push", "bare-merge", "guard-crash", "builder-test-edit", "test-author-scope",
    "record-writer-scope", "author-diff", "builder-diff", "writer-diff",
    "role-diff-main-checkout", "role-diff-unresolved")


class GuardRuleNamesTests(unittest.TestCase):
    """`guard_rule_names(text)` reads rule ids out of guard source with `ast`."""

    ids = staticmethod(rule_audit.guard_rule_names)

    def test_each_call_and_table_shape_that_writes_an_id_is_read(self):
        src = (
            'ask_command("force-push", REASON, "git push", "forced push")\n'
            'ask_command("bare-merge", REASON, "gh pr merge 1", "bare merge")\n'
            'record(str(payload.get("tool_name", "")), "crash", "guard-crash", why)\n'
            'record("SubagentStop", "noted", "role-diff-main-checkout", where)\n'
            'record("SubagentStop", "noted", "role-diff-unresolved", found)\n'
            'def diff_rule(role):\n'
            '    """A docstring that says "ghost-diff" names no id."""\n'
            '    return {A: "author-diff", W: "writer-diff"}.get(role, "builder-diff")\n'
            'code, why = {A: ("test-author-scope", R1), W: ("record-writer-scope", R2)}'
            '.get(role, ("builder-test-edit", R3))\n')
        self.assertEqual(self.ids(src), set(GUARD_IDS_THE_REGEX_MISSED))

    def test_a_variable_rule_names_no_id(self):
        self.assertEqual(self.ids("record(tool, decision, rule, matched)\nrefuse(tool, 'deny', code, R, m)\n"), set())

    def test_a_comment_that_shows_a_call_names_no_id(self):
        self.assertEqual(self.ids('# refuse(tool, "deny", "ghost-rule", R, m)\n'), set())

    def test_a_comment_opener_inside_a_string_hides_no_call(self):
        src = ('record(tool, "noted", "a-rule", "// not a comment /* nor this */ # nor this")\n'
               'refuse(tool, "deny", "b-rule", "x", "y")\n')
        self.assertEqual(self.ids(src), {"a-rule", "b-rule"})

    def test_a_multi_line_string_that_only_shows_a_call_names_no_id(self):
        src = ('DOC = """\nrefuse(tool, "deny", "ghost-rule", R, m)\n"""\n'
               'record(tool, "noted", "real-rule", "m")\n')
        self.assertEqual(self.ids(src), {"real-rule"})

    def test_a_lone_quote_in_text_hides_no_call(self):
        src = ('# don\'t stop here\nNOTE = "it\'s"\n"""Don\'t"""\n'
               'refuse(tool, "deny", "after-quote", NOTE, "m")\n')
        self.assertEqual(self.ids(src), {"after-quote"})

    def found_or_loud(self, src, wanted):
        """A call the reader cannot place by position is found, or the reader refuses it. It is never
        dropped without a word: a rule that can fire but is not listed hides from a never-fired cull."""
        try:
            ids = self.ids(src)
        except Exception:
            return  # loud
        self.assertTrue(any(wanted in i for i in ids), "dropped without a word: %r from %r" % (ids, src))

    def test_found_or_loud_is_not_vacuous(self):
        self.found_or_loud('refuse(tool, "deny", "lit-rule", R, m)\n', "lit-rule")
        with self.assertRaises(AssertionError):
            self.found_or_loud('refuse(tool, "deny", "lit-rule", R, m)\n', "another-rule")

    def test_a_keyword_rule_id_is_found_or_the_reader_refuses_it(self):
        self.found_or_loud('refuse(tool, "deny", rule="kw-rule", reason=R, matched=m)\n', "kw-rule")
        self.found_or_loud('ask_command(rule="kw-ask", reason=R)\n', "kw-ask")

    def test_an_f_string_rule_id_is_found_or_the_reader_refuses_it(self):
        self.found_or_loud('refuse(tool, "deny", f"fs-{n}", R, m)\n', "fs-")
        self.found_or_loud('record(tool, "noted", f"plain-fs", "m")\n', "plain-fs")


class EmittedRuleIdsTests(unittest.TestCase):
    """`emitted_rule_ids(root)` is the one list of every id the guard and the other guards write to guard.log."""

    def test_the_real_source_yields_every_id_the_old_regex_missed(self):
        ids = rule_audit.emitted_rule_ids()
        self.assertEqual(sorted(set(GUARD_IDS_THE_REGEX_MISSED) - ids), [])

    def files(self):
        refuse = 'refuse(tool, "deny", "%s", REASON, matched)\n'
        return {
            os.path.join("hooks", "guard.py"): refuse % "main-rule",
            os.path.join("hooks", "guard_x.py"): 'ask_command("sibling-rule", R, "m", "l")\n',
            os.path.join("hooks", "test_guard.py"): refuse % "test-only-rule",
            os.path.join("lint", "_transcript.py"): 'X = 1\n',
        }

    def ids_of(self, files):
        """The ids of a fixture root. A crash is a failure that names its cause: the root has no
        guard file, because no hook writes an STE id now (decision ste-guard-fixes-not-nags)."""
        try:
            return rule_audit.emitted_rule_ids(GuardTextTests.tree(self, files))
        except FileNotFoundError as e:
            self.fail("emitted_rule_ids reads a guard file the root does not have: %s" % e)

    def test_a_fixture_root_gives_guard_siblings_config_watch_and_no_test_file_and_no_ste_code(self):
        files = self.files()
        files[os.path.join("hooks", "config_watch.py")] = 'record("ConfigChange", "reverted", "watch-rule", "m")\n'
        ids = self.ids_of(files)
        for wanted in ("main-rule", "sibling-rule", "watch-rule"):
            self.assertIn(wanted, ids)
        self.assertNotIn("test-only-rule", ids)
        self.assertEqual(sorted(i for i in ids if i.startswith("STE")), [],
                         "no hook writes an STE code to guard.log, so a cull would call each one never-fired")

    def test_the_real_source_holds_no_ste_code(self):
        self.assertEqual(sorted(i for i in rule_audit.emitted_rule_ids() if i.startswith("STE")), [])

    def test_a_leftover_ste_gate_file_adds_no_id(self):
        files = self.files()
        files[os.path.join("lint", "ste_gate.py")] = 'LOG = "STE-fallback"\n'
        ids = self.ids_of(files)
        self.assertNotIn("STE-fallback", ids)

    def test_a_root_with_no_config_watch_is_read_without_it(self):
        ids = self.ids_of(self.files())
        self.assertIn("main-rule", ids)
        self.assertNotIn("watch-rule", ids)


# ------------------------------------------------------------ refusal cites
# A refusal prints a cite: `decision <slug>` for a file in docs/decisions/, or `rule <anchor>` for
# a `<!-- rule:<anchor> -->` in CLAUDE.md or output-styles/*.md. Both sets are read live. A refusal
# site is a refuse() or ask_command() call, a raw permissionDecision dict, a raise or return of a
# Stop, a refuse print (a decision "block" that reaches the output), or a block dict that a call passes
# to a helper which prints that parameter. Whatever the hook event.
# The scan reads hooks/*.py, merge/merge.py and each .py script settings.json wires. A refusal id
# with a site that prints no cite, or whose reason the scan cannot read, fails unless it is in
# REFUSAL_UNCITED_EXEMPT with its home. The exempt list only shrinks.

CITE_RE = re.compile(r"\b(decision|rule) ([a-z0-9][a-z0-9-]*)\b")
HOME_RE = re.compile(r"[a-z0-9][a-z0-9-]*")
MAX_DEPTH = 24  # hops a read may follow: report_guard's 3100 needs 16. Scan time grows steeply above 32.
PENDING_ASK = "PENDING_ASK"  # filled only by ask_command(), whose literal call sites are scanned
EXEMPT_REASON_WORDS = 6  # the least words an exempt entry's reason may have

# Refusal id -> its home (a step slug or debt id), for an id that still prints no cite. An entry is the home
# alone, or (home, reason) for an id that names its reason; a function key (see refusal_problems) always names
# one. The refusal-vs-rule record gives the uncited rule rewrites to refusal-uncited-rewrites, agent-model-cap
# to refusal-looser-fixes, and the rest to the sweep step refusal-matches-rule.
REFUSAL_UNCITED_EXEMPT = {
    "gh-login-switch": ("refusal-uncited-rewrites", "a gh command runs as the active login on the owner's computer; the reason states it but cites no decision"),
    "handoff-unread": ("refusal-uncited-rewrites", "a call waits until the session reads its handoff after compaction; the reason states it but cites no decision"),
    "merge-role-proof": ("refusal-uncited-rewrites", "a session must prove its merge tier from its own record; the reason states it but cites no decision"),
    "option-letter-keys": ("refusal-uncited-rewrites", "each option's key is the letter for its position; the reason states it but cites no decision"),
    "question-departs": ("refusal-uncited-rewrites", "a question says how the work departs from main; the reason states it but cites no decision"),
    "rework-off-page": ("refusal-uncited-rewrites", "an open item never says it is being reworked; the reason states it but cites no decision"),
    "trust-card-in-build": ("refusal-uncited-rewrites", "a card-opening call needs a record that proves no build tag; the reason states it but cites no decision"),
    "agent-model-floor": "refusal-matches-rule",
    "background-end": "refusal-matches-rule",
    "command-in-item": "refusal-matches-rule",
    "designer-scope": "refusal-matches-rule",
    "destructive-delete": "refusal-matches-rule",
    "draft-pr": "refusal-matches-rule",
    "force-push": "refusal-matches-rule",
    "frozen-path": "refusal-matches-rule",
    "hand-made-worktree": "refusal-matches-rule",
    "impeccable-review-only": "refusal-matches-rule",
    "live-stream": "refusal-matches-rule",
    "ln-over-directory": "refusal-uncited-rewrites",
    "machine-wide-kill": "refusal-matches-rule",
    "merge-checks": "refusal-matches-rule",
    "other-checkout": "refusal-matches-rule",
    "playwright-browsers-path": "refusal-matches-rule",
    "playwright-install": "refusal-matches-rule",
    "port-question": "refusal-matches-rule",
    "press-link": "refusal-matches-rule",
    "question-form": "refusal-matches-rule",
    "record-writer-scope": "refusal-matches-rule",
    "records-page": "refusal-matches-rule",
    "rm-after-cd": "refusal-matches-rule",
    "rm-var-unguarded": "refusal-matches-rule",
    "roles-third-round-steps-up": "refusal-matches-rule",
    "session-home": "refusal-matches-rule",
    "shared-tree": "refusal-matches-rule",
    "silent-write": "refusal-matches-rule",
    "simulator-boot-cap": "refusal-matches-rule",
    "simulator-boot-twin": "refusal-matches-rule",
    "task-names-check": "refusal-matches-rule",
    "test-author-scope": "refusal-matches-rule",
    "uniform-pick": "refusal-matches-rule",
    "waiter": "refusal-matches-rule",
    "worktree-home": "refusal-matches-rule",
    "wsl-allow-list": "refusal-matches-rule",
    # merge/merge.py. A key is `merge:<function>: <text prefix>`, and names one uncited site of that function by
    # the start of its message. Its reason says why the message names no decision or rule. A key that names
    # several identical sites gives their count as the third entry.
    "merge:Host.base_state: out": ("refusal-matches-rule", "the base state read failed, and the stop prints gh's output unchanged"),
    "merge:Host.gh: network error from `gh": ("refusal-matches-rule", "gh failed on a network error after its retries, and the stop prints gh's output"),
    "merge:Host.pages: reading from GitHub failed": ("refusal-matches-rule", "a repo file could not be read from GitHub, and the stop names the file and the error"),
    "merge:Host.pr: reading the pull request failed": ("refusal-matches-rule", "the pull request could not be read, and the stop prints gh's output"),
    "merge:Host.pr_number: no pull request is named": ("refusal-matches-rule", "no pull request is named and the branch cannot be read, so the stop prints git's output"),
    "merge:Host.pr_number: open pull requests have the head": ("refusal-matches-rule", "more than one open pull request has the same head, so the stop names the branch"),
    "merge:Host.required_names: merge.ignoreChecks names a required check": ("refusal-matches-rule", "the config names a required check to ignore, and the stop states that rule with no decision cite"),
    "merge:base_job_caps: cannot read to look for .github/workflows": ("refusal-matches-rule", "the workflow folder on the base could not be listed, and the stop prints git's output"),
    "merge:base_verdict: cannot read origin/ to look for .github/workflows": ("refusal-matches-rule", "the workflow folder on the base could not be listed, and the stop prints git's output"),
    "merge:confirm: the pull request is": ("refusal-matches-rule", "the pull request is closed or conflicting, and the stop names GitHub's state"),
    "merge:confirm: the push of was refused": ("refusal-matches-rule", "a plain push was refused, so nothing reaches origin, and the stop prints only that", 2),
    "merge:confirm: why": ("refusal-matches-rule", "the check wait's reason is a Host method's return, which the reader cannot follow"),
    "merge:confirm: merge: the worktree is gone": ("refusal-matches-rule", "the worktree is gone, so the claim cannot be reverted, and the stop names the claim and the branch"),
    "merge:confirm: unexpected after the claim was pushed": ("refusal-matches-rule", "an error that is not a Stop hit the run after the claim, and the stop prints its name and text"),
    "merge:confirm: unexpected after the claim was pushed: merge: the worktree is gone": ("refusal-matches-rule", "the same unexpected error with the worktree gone, so the claim stays on the branch"),
    "merge:confirm: the local main did not move in": ("refusal-matches-rule", "the local main cannot fast-forward in that tree, so the stop names the fix by hand"),
    "merge:confirm: is not on . Nothing was moved": ("refusal-matches-rule", "the commit is not on origin, so no local move was made, and the stop names only that"),
    "merge:confirm: is not on origin/. Nothing was moved": ("refusal-matches-rule", "the commit is not on origin's base, so no local move was made, and the stop names only that"),
    "merge:draft_step: the push of was refused": ("refusal-matches-rule", "a plain push was refused, so nothing reaches origin, and the stop prints only that"),
    "merge:ff_main: git fetch origin failed, so the local main": ("refusal-matches-rule", "git fetch failed, so the local main cannot be moved, and the stop prints git's output"),
    "merge:host_default_branch: network error from `gh api repos`": ("refusal-matches-rule", "gh failed on a network error after its retries, and the stop says to run again"),
    "merge:host_default_branch: the default branch cannot be read from gh": ("refusal-matches-rule", "gh could not give the default branch, and the stop prints the error"),
    "merge:ignore_checks: merge.ignoreChecks entry needs a name": ("refusal-matches-rule", "a merge.ignoreChecks entry has no name or no reason, and the stop names the config entry"),
    "merge:load_config: cannot read on origin/":("refusal-matches-rule", "a config or workflow file cannot be read on the base, and the stop prints the read's error"),
    "merge:main: not in a git checkout": ("refusal-matches-rule", "the run is not in a git checkout, so no merge can start, and the stop names no decision"),
    "merge:main: the pull request is": ("refusal-matches-rule", "the pull request is closed or conflicting, and the stop names GitHub's state"),
    "merge:main: on origin/: defaultBranch must be a non-empty string": ("refusal-matches-rule", "the merge config on the base names no usable default branch, and the stop names the field"),
    "merge:main: on origin/: merge. is not valid": ("refusal-matches-rule", "a merge config field on the base holds a value the tool refuses, and the stop names the field"),
    "merge:main: on origin/: merge.deadlineMinutes must be a whole number": ("refusal-matches-rule", "the merge deadline on the base is not a whole number from 1 to 360, and the stop names it"),
    "merge:main: on origin/: merge.ignoreChecks must be a list": ("refusal-matches-rule", "the merge ignoreChecks on the base is not a list, and the stop names the field"),
    "merge:main: on origin/ has an unknown field": ("refusal-matches-rule", "the merge block on the base holds a field the tool does not read, and the stop names it"),
    "merge:main: cannot read the config on origin/": ("refusal-matches-rule", "the config file cannot be read on the base, and the stop prints the read's error"),
    "merge:main: cannot read origin/ to look for": ("refusal-matches-rule", "the config folder on the base cannot be listed, and the stop prints git's output"),
    "merge:main: git fetch origin failed": ("refusal-matches-rule", "git fetch failed, so the base cannot be read, and the stop prints git's output"),
    "merge:add_worktree: cannot make the worktree": ("refusal-matches-rule", "git could not add the worktree, and the stop prints git's output"),
    "merge:preview: the pull request is": ("refusal-matches-rule", "the pull request is closed or conflicting, and the stop names GitHub's state"),
    "merge:prove: network error on the fetch of origin": ("refusal-matches-rule", "a network error hit the fetch of the base after its retries, and the claim stays on the branch"),
}


def cite_homes(root=rule_audit.ROOT):
    """-> (decision slugs, rule anchors), read from the repo as it is now. The anchors are read from every
    RULE_FILES entry, the one list of rule files, so an anchor that moves to a skill is still a home."""
    decisions_dir = os.path.join(root, "docs", "decisions")
    decisions = {name[:-3] for name in os.listdir(decisions_dir) if name.endswith(".md")}
    return decisions, set(rule_audit.claude_md_anchors(rule_audit.rule_text(root)))


def cites(text, homes):
    decisions, anchors = homes
    return any(slug in (decisions if kind == "decision" else anchors) for kind, slug in CITE_RE.findall(text))


def _own(node):
    """The nodes that run in `node`'s own scope: not the bodies of the functions or classes it defines."""
    stack = list(ast.iter_child_nodes(node))
    while stack:
        child = stack.pop()
        yield child
        if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            stack.extend(ast.iter_child_nodes(child))


def _bound_names(target):
    return [n.id for n in ast.walk(target) if isinstance(n, ast.Name)]


def _branch_chain(node, mod):
    """The `if` arms that hold `node`, outermost first: (id of the `if`, "body" or "orelse") for each `if` whose
    body or else holds it. An `if`'s test runs before either arm, so the test adds none."""
    chain, cur = [], node
    parent = mod.parents.get(id(cur))
    while parent is not None:
        if isinstance(parent, ast.If) and cur in parent.body:
            chain.append((id(parent), "body"))
        elif isinstance(parent, ast.If) and cur in parent.orelse:
            chain.append((id(parent), "orelse"))
        cur, parent = parent, mod.parents.get(id(parent))
    return tuple(reversed(chain))


def _sibling(binding, read):
    """True when two arm chains first split at one `if`, one in its body and the other in its else (an elif is one)."""
    for (b_if, b_arm), (r_if, r_arm) in zip(binding, read):
        if b_if != r_if:
            return False  # two `if` statements in a row: the earlier one runs first
        if b_arm != r_arm:
            return True
    return False


def _effect(at):
    """Where a binding takes effect in source order: an assignment at its end, since its value runs first, else at its
    start. None is an argument, which binds on entry."""
    if at is None:
        return (0, 0)
    if isinstance(at, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.NamedExpr)):
        return (at.end_lineno, at.end_col_offset)
    return (at.lineno, at.col_offset)


def _loops_holding(node, mod):
    """The loops that run `node` again: a for body, and a while test or body, within its own def."""
    loops, cur = [], node
    parent = mod.parents.get(id(cur))
    while parent is not None and not isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        if isinstance(parent, (ast.For, ast.AsyncFor, ast.While)) and (
                any(cur is s for s in parent.body) or cur is getattr(parent, "test", None)):
            loops.append(parent)
        cur, parent = parent, mod.parents.get(id(parent))
    return loops


def _statement(node, mod):
    """The statement `node` sits in: the node itself when it is one, else the nearest statement above it."""
    cur = node
    while cur is not None and not isinstance(cur, ast.stmt):
        cur = mod.parents.get(id(cur))
    return cur


def _deferred(node, mod):
    """True when a lambda or a generator expression within `node`'s own def holds it. Each runs later than its
    statement, when it is called or pulled, so it may read a binding made after its statement."""
    cur = mod.parents.get(id(node))
    while cur is not None and not isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        if isinstance(cur, (ast.Lambda, ast.GeneratorExp)):
            return True
        cur = mod.parents.get(id(cur))
    return False


def _enclosing_defs(node, mod):
    """The defs around `node`, nearest first. A class body is no scope for a def inside it, so it is skipped."""
    out, cur = [], mod.parents.get(id(node))
    while cur is not None:
        if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append(cur)
        cur = mod.parents.get(id(cur))
    return out


def _holds(outer, node, mod):
    """True when `node` is `outer` or sits inside it."""
    cur = node
    while cur is not None:
        if cur is outer:
            return True
        cur = mod.parents.get(id(cur))
    return False


def _runs_on_every_path(at, read, mod, scope):
    """True when the statement `at` runs on every path to `read` in `scope`: no branch, loop or handler between them
    holds `at` and not `read`. A loop or handler that holds `at` is never every path, so its target does not count."""
    node = at
    while node is not None and node is not scope:
        if isinstance(node, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.ExceptHandler)) \
                and not _holds(node, read, mod):
            return False
        node = mod.parents.get(id(node))
    return True


def _reaching(entries, read, mod):
    """The bindings a read sees. Where a read runs in a lambda or a generator expression, all of them: it may run after any of them. Else
    one reaches the read when it sits in the read's own statement, or when it takes effect before the read and is not
    in an arm of an `if` the read is not in. A binding after the read, or in a sibling arm, never ran before it. A loop
    body that holds both pools them all, since the loop may run the binding again before the read. A run-time binding
    that reaches the read still leaves it unresolved. When unsure, a binding stays in."""
    if _deferred(read, mod):
        return list(entries)
    loops = {id(loop) for loop in _loops_holding(read, mod)}
    chain = _branch_chain(read, mod)
    before = (read.lineno, read.col_offset)
    statement = _statement(read, mod)
    found = []
    for entry in entries:
        at = entry[2]
        if at is None:
            found.append(entry)
        elif _statement(at, mod) is statement:
            found.append(entry)  # one statement runs its parts in an order the source does not show
        elif loops & {id(loop) for loop in _loops_holding(at, mod)}:
            found.append(entry)
        elif _effect(at) < before and not _sibling(_branch_chain(at, mod), chain):
            found.append(entry)
    return found


def _locals(fdef, mod):
    """name -> [(value, slot, at)] for each binding in a function. A value of None is a binding made at
    run time (an argument, a loop target), so the name has no static text. A slot is the position
    in a tuple value that the name unpacks. `at` is the node the binding takes effect at (see _effect),
    and None for an argument, which binds on entry."""
    locs = {}

    def bind(name, value, slot, at):
        locs.setdefault(name, []).append((value, slot, at))

    args = fdef.args
    for arg in args.posonlyargs + args.args + args.kwonlyargs + [a for a in (args.vararg, args.kwarg) if a]:
        locs.setdefault(arg.arg, []).append((None, None, None))
    for node in _own(fdef):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    bind(target.id, node.value, None, node)
                elif isinstance(target, ast.Tuple) and all(isinstance(e, ast.Name) for e in target.elts):
                    for i, e in enumerate(target.elts):
                        bind(e.id, node.value, i, node)
                else:
                    for name in _bound_names(target):
                        bind(name, None, None, node)
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            for name in _bound_names(node.target):
                bind(name, None, None, node.target)  # the target binds as the body starts
        elif isinstance(node, ast.comprehension):
            for name in _bound_names(node.target):
                bind(name, None, None, mod.parents.get(id(node)))  # the comprehension binds before its element is read
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign, ast.NamedExpr)):
            for name in _bound_names(node.target):
                bind(name, None, None, node)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                for name in _bound_names(item.optional_vars) if item.optional_vars else []:
                    bind(name, None, None, item.optional_vars)
        elif isinstance(node, ast.Lambda):
            # A lambda's parameters bind at run time. Its body is read in this scope, so they read as unknown.
            for arg in node.args.posonlyargs + node.args.args + node.args.kwonlyargs + [a for a in (node.args.vararg, node.args.kwarg) if a]:
                bind(arg.arg, None, None, arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bind(node.name, None, None, node)  # the caught exception is bound at run time
    return locs


def _caught_as_stop(node, name, mod):
    """True when the nearest `except` clause above `node`, in its own def, binds `name` and catches only Stop
    classes, alone or in a tuple whose every member is a Stop class name. Another clause that binds the same name
    does not count: its exception is not a Stop."""
    cur = mod.parents.get(id(node))
    while cur is not None and not isinstance(cur, ast.FunctionDef):
        if isinstance(cur, ast.ExceptHandler) and cur.name == name:
            caught = cur.type.elts if isinstance(cur.type, ast.Tuple) else [cur.type]
            return bool(caught) and all(isinstance(c, ast.Name) and c.id in mod.stops for c in caught)
        cur = mod.parents.get(id(cur))
    return False


class _Fixed:
    """A parameter's text, bound to the text its call's argument reads as. None when the argument is run-time."""

    def __init__(self, texts):
        self.texts = texts


def _param_names(fdef):
    a = fdef.args
    return [x.arg for x in a.posonlyargs + a.args + a.kwonlyargs]


def _call_args(call, fdef):
    """(parameter, argument expression) for each argument a call passes. A keyword names its parameter."""
    a = fdef.args
    pairs = list(zip([x.arg for x in a.posonlyargs + a.args], call.args))
    return pairs + [(k.arg, k.value) for k in call.keywords if k.arg]


def _unparse(node):
    return ast.unparse(node)


def _union(parts):
    """Join the alternatives of several branches. None when a branch is read only at run time, so
    the reason is not read at all. A branch that is [] never yields text, and adds nothing."""
    if any(part is None for part in parts):
        return None
    return [text for part in parts for text in part]


def _dict_get_options(call):
    """The values that `{...}.get(key, default)` can return, or None when the call is no such call."""
    func = call.func
    if isinstance(func, ast.Attribute) and func.attr == "get" and isinstance(func.value, ast.Dict):
        return list(func.value.values) + call.args[1:2]
    return None


def _join_parts(call):
    """(separator, elements) of `"<sep>".join([...])` or `"<sep>".join((...))` with a literal separator, else None."""
    func = call.func
    if not (isinstance(func, ast.Attribute) and func.attr == "join" and isinstance(func.value, ast.Constant)
            and isinstance(func.value.value, str) and len(call.args) == 1 and not call.keywords
            and isinstance(call.args[0], (ast.List, ast.Tuple))):
        return None
    return func.value.value, call.args[0].elts


class _Module:
    """One hooks module, read with ast: its module-level values, its functions and its imports."""

    def __init__(self, name, text):
        self.name = name
        self.tree = ast.parse(text)
        self.values = {}
        self.defs = {}
        self.from_names = {}
        self.module_alias = {}
        for node in _own(self.tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.values.setdefault(target.id, []).append(node.value)
                    elif isinstance(target, ast.Tuple) and isinstance(node.value, ast.Tuple) \
                            and len(target.elts) == len(node.value.elts):  # `A, B = "x", "y"`
                        for name, value in zip(target.elts, node.value.elts):
                            if isinstance(name, ast.Name):
                                self.values.setdefault(name.id, []).append(value)
            elif isinstance(node, ast.FunctionDef):
                self.defs[node.name] = node
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                for alias in node.names:
                    self.from_names[alias.asname or alias.name] = (node.module.split(".")[-1], alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    self.module_alias[alias.asname or alias.name] = alias.name.split(".")[-1]
        self.parents, self.name_loads = {}, {}
        for node in ast.walk(self.tree):
            for child in ast.iter_child_nodes(node):
                self.parents[id(child)] = node
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                self.name_loads.setdefault(node.id, []).append(node)
        self.stops = _stop_classes(self)  # the Stop classes of this module, read below
        self.flow_memo = {}  # the output reads of this module, once each (see _reaches_output)


class _Reasons:
    """The static text a reason expression can take, followed across the modules in `world`.
    -> a list with one string per branch, or None when some piece is known only at run time."""

    def __init__(self, world):
        self.world = world
        self._locals = {}
        self._memo = {}  # (read, ids of its node, module, locals, depth) -> (result, the objects those ids name)
        self._no_locals = {}  # the locals of a module-level value; never written, so one object serves every read

    def locals_of(self, fdef, mod):
        if id(fdef) not in self._locals:
            self._locals[id(fdef)] = _locals(fdef, mod)
        return self._locals[id(fdef)]

    def _memo_read(self, key, keep, compute):
        """The result of one read, computed once per key. A read repeats the same sub-reads once per branch it
        takes, so without this the cost grows with the depth cap. `keep` holds the objects whose ids the key
        names, so no id is reused while the memo lives. A list result is copied, so no caller can change it."""
        if key not in self._memo:
            self._memo[key] = (compute(), keep)
        result = self._memo[key][0]
        return None if result is None else list(result)

    def alts(self, expr, mod, locs, depth=0):
        return self._memo_read(("alts", id(expr), id(mod), id(locs), depth), (expr, mod, locs),
                               lambda: self._alts(expr, mod, locs, depth))

    def _alts(self, expr, mod, locs, depth):
        if depth > MAX_DEPTH:
            return None
        d = depth + 1
        if isinstance(expr, _Fixed):  # a parameter, bound to the text of its call's argument
            return expr.texts
        if isinstance(expr, ast.Constant):
            if expr.value is None or expr.value == "":  # a falsy branch: the caller tests it before refusing
                return []
            return [expr.value] if isinstance(expr.value, str) else None
        if isinstance(expr, ast.JoinedStr):
            # An f-string keeps its static pieces; a `{name}` that holds static text adds that text, and
            # a run-time piece adds none, as in a join.
            texts, piece_static = [""], False
            for v in expr.values:
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    options = [v.value]
                else:
                    options = self.alts(v.value, mod, locs, d) if isinstance(v, ast.FormattedValue) else None
                    options = options or [""]
                piece_static = piece_static or any(options)
                texts = [a + b for a in texts for b in options]
            return texts if piece_static and any(texts) else None
        if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Mod):  # the arguments of `%` carry no text
            return self.alts(expr.left, mod, locs, d)
        if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Add):
            # A run-time piece in a join adds no static text; the static pieces around it still count.
            left, right = self._piece(expr.left, mod, locs, d), self._piece(expr.right, mod, locs, d)
            if left == [] or right == []:
                return []
            if left is None and right is None:
                return None
            # A name bound at run time in one branch and to static text in another: the run-time branch
            # joins as above, and each static branch stands alone, since it replaces the run-time piece
            # and must cite by itself (a judge hook's fallback reason).
            apart = []
            for piece, text in ((expr.left, left), (expr.right, right)):
                if text is None and isinstance(piece, ast.Name):
                    apart += self._static_branches(piece.id, mod, locs, d)
            left, right = left or [""], right or [""]
            return [a + b for a in left for b in right] + apart
        if isinstance(expr, ast.IfExp):
            return _union([self.alts(expr.body, mod, locs, d), self.alts(expr.orelse, mod, locs, d)])
        if isinstance(expr, ast.Name):
            return self._name(expr, mod, locs, d, None)
        if isinstance(expr, ast.Subscript):
            if isinstance(expr.slice, ast.Constant) and isinstance(expr.slice.value, int) and expr.slice.value >= 0:
                return self._elt(expr.value, expr.slice.value, mod, locs, d)  # `reason[0]` of a tuple-valued name
            return self._dict(expr, mod, locs, d)
        if isinstance(expr, ast.Call):
            if isinstance(expr.func, ast.Attribute) and expr.func.attr == "format":
                return self.alts(expr.func.value, mod, locs, d)
            joined = _join_parts(expr)
            if joined is not None:
                return self._join(joined[0], joined[1], mod, locs, d)
            options = _dict_get_options(expr)
            if options is not None:
                return _union([self.alts(o, mod, locs, d) for o in options])
            if isinstance(expr.func, ast.Name) and expr.args and not expr.keywords:
                if expr.func.id == "str" and len(expr.args) == 1:  # a refusal's text, read as its argument
                    arg = expr.args[0]
                    if isinstance(arg, ast.Name) and _caught_as_stop(expr, arg.id, mod):
                        return []  # a Stop caught and printed again: its origin is a site of its own
                    return self.alts(arg, mod, locs, d)
                if expr.func.id in mod.stops:  # `Stop(text)` as a value: the text it carries
                    return self.alts(expr.args[0], mod, locs, d)
            return self._call(expr, mod, locs, d, None)
        return None

    def _piece(self, expr, mod, locs, depth, branch=False):
        """An operand of `+`. A falsy branch of an `if` operand is the join without that piece, so it reads as "" and
        not as no text: `join + (TAIL if c else "")` reads the join alone when `c` is false. A falsy operand on its
        own still reads no text, as a falsy whole reason does."""
        if isinstance(expr, ast.IfExp):
            return _union([self._piece(b, mod, locs, depth, True) for b in (expr.body, expr.orelse)])
        if branch and isinstance(expr, ast.Constant) and expr.value == "":
            return [""]
        return self.alts(expr, mod, locs, depth)

    def _static_branches(self, name, mod, locs, depth):
        """The static text of a local name's branches, skipping the run-time ones. `x = x or "text"` adds
        "text": its `x` is the run-time branch that another binding holds."""
        found = []
        for value, slot, _ in locs.get(name, []):
            if isinstance(value, ast.BoolOp) and isinstance(value.op, ast.Or) \
                    and isinstance(value.values[0], ast.Name) and value.values[0].id == name:
                parts = [self.alts(v, mod, locs, depth) for v in value.values[1:]]
            elif value is not None and slot is None:
                parts = [self.alts(value, mod, locs, depth)]
            else:
                parts = []
            found += [t for part in parts for t in (part or [])]
        return found

    def _join(self, sep, elts, mod, locs, depth):
        """The text of `sep.join(elts)`: the branches of each element, joined by `sep`. A starred element, or one
        with no static text at run time, adds an empty piece, as a run-time piece does in a `+` chain. A join
        with no static piece reads no text."""
        pieces, static = [], False
        for e in elts:
            options = None if isinstance(e, ast.Starred) else self.alts(e, mod, locs, depth)
            static = static or any(options or [])
            pieces.append(options or [""])
        if not static:
            return None
        texts = None
        for options in pieces:
            texts = list(options) if texts is None else [a + sep + b for a in texts for b in options]
        return texts

    def _value(self, value, slot, index, mod, locs, depth):
        if slot is not None:
            return self._elt(value, slot, mod, locs, depth)
        if index is not None:
            return self._elt(value, index, mod, locs, depth)
        return self.alts(value, mod, locs, depth)

    def _elt(self, expr, i, mod, locs, depth):
        """The text of element `i` of a tuple-valued expression."""
        return self._memo_read(("elt", id(expr), i, id(mod), id(locs), depth), (expr, mod, locs),
                               lambda: self._elt_of(expr, i, mod, locs, depth))

    def _elt_of(self, expr, i, mod, locs, depth):
        if depth > MAX_DEPTH:
            return None
        d = depth + 1
        if isinstance(expr, ast.Constant) and expr.value is None:  # `return None`: no tuple, so no element
            return []
        if isinstance(expr, ast.Tuple):
            return self.alts(expr.elts[i], mod, locs, d) if i < len(expr.elts) else None
        if isinstance(expr, ast.IfExp):
            return _union([self._elt(expr.body, i, mod, locs, d), self._elt(expr.orelse, i, mod, locs, d)])
        if isinstance(expr, ast.Call):
            options = _dict_get_options(expr)
            if options is not None:
                return _union([self._elt(o, i, mod, locs, d) for o in options])
            if isinstance(expr.func, ast.Name):
                return self._call(expr, mod, locs, d, i)
            return None
        if isinstance(expr, ast.Name):
            return self._name(expr, mod, locs, d, i)
        return None

    def _name(self, read, mod, locs, depth, index):
        name = read.id
        if name in locs:
            seen = _reaching(locs[name], read, mod)
            if not seen:  # bound in this def, but no binding reaches this read: its text is unknown
                return None
            return _union([self._value(v, slot, index, mod, locs, depth) if v is not None else None
                           for v, slot, _ in seen])
        for outer in _enclosing_defs(read, mod):  # a nested def reads the enclosing def's bindings, all of them
            outer_locs = self.locals_of(outer, mod)
            if name in outer_locs:
                return _union([self._value(v, slot, index, mod, outer_locs, depth) if v is not None else None
                               for v, slot, _ in outer_locs[name]])
        home = self._home(mod, name)
        if home is None:
            return None
        hmod, values = home
        return _union([self._value(v, None, index, hmod, self._no_locals, depth) for v in values])

    def _home(self, mod, name, depth=0):
        """(module, values) where a module-level name is bound, following `from` imports."""
        if name in mod.values:
            return mod, mod.values[name]
        if name in mod.from_names and depth < MAX_DEPTH and mod.from_names[name][0] in self.world:
            src, orig = mod.from_names[name]
            return self._home(self.world[src], orig, depth + 1)
        return None

    def _function(self, name, mod, depth=0):
        if name in mod.defs:
            return mod, mod.defs[name]
        if name in mod.from_names and depth < MAX_DEPTH and mod.from_names[name][0] in self.world:
            src, orig = mod.from_names[name]
            return self._function(orig, self.world[src], depth + 1)
        return None

    def _call(self, call, mod, locs, depth, index):
        """The reason a call returns: each return value, or element `index` of each return tuple. The
        parameters the call passes read as their arguments, read in the caller's scope."""
        return self._memo_read(("call", id(call), id(mod), id(locs), depth, index), (call, mod, locs),
                               lambda: self._call_of(call, mod, locs, depth, index))

    def _call_of(self, call, mod, locs, depth, index):
        if not isinstance(call.func, ast.Name) or depth > MAX_DEPTH:
            return None
        found = self._function(call.func.id, mod)
        if found is None:
            return None
        fmod, fdef = found
        flocs = dict(self.locals_of(fdef, fmod))
        if not any(isinstance(a, ast.Starred) for a in call.args) and not any(k.arg is None for k in call.keywords):
            for name, arg in _call_args(call, fdef):
                if name in flocs:
                    flocs[name] = [(_Fixed(self.alts(arg, mod, locs, depth + 1)), None, None)]
        returns = [n.value for n in _own(fdef) if isinstance(n, ast.Return) and n.value is not None]
        return _union([self._value(v, None, index, fmod, flocs, depth + 1) for v in returns])

    def _dict(self, sub, mod, locs, depth):
        """`TABLE["key"]` or `module.TABLE["key"]`, where TABLE is a module-level dict literal."""
        if not isinstance(sub.slice, ast.Constant):
            return None
        base = sub.value
        if isinstance(base, ast.Attribute) and isinstance(base.value, ast.Name) and base.value.id in mod.module_alias:
            owner, name = self.world.get(mod.module_alias[base.value.id]), base.attr
        elif isinstance(base, ast.Name):
            owner, name = mod, base.id
        else:
            return None
        home = self._home(owner, name) if owner is not None else None
        if home is None or len(home[1]) != 1 or not isinstance(home[1][0], ast.Dict):
            return None
        hmod, table = home[0], home[1][0]
        for key, value in zip(table.keys, table.values):
            if self._key_text(key, hmod) == sub.slice.value:
                return self.alts(value, hmod, self._no_locals, depth + 1)
        return None

    def _key_text(self, key, mod):
        """A dict key's text: a string literal, or a module-level name bound to one."""
        if isinstance(key, ast.Name):
            home = self._home(mod, key.id)
            if home is None or len(home[1]) != 1:
                return None
            key = home[1][0]
        return key.value if isinstance(key, ast.Constant) and isinstance(key.value, str) else None


def _tuple_options(expr):
    """The tuple options a table value holds: a dict's values, or a `.get` call's values and default.
    None when an option is not a tuple, so the scan cannot read its ids."""
    if isinstance(expr, ast.Tuple):
        return [expr]
    if isinstance(expr, ast.Dict):
        options = list(expr.values)
    else:
        options = _dict_get_options(expr) if isinstance(expr, ast.Call) else None
        if options is None:
            return None
    return options if all(isinstance(o, ast.Tuple) for o in options) else None


# Parameter names of refuse() and ask_command(), used when a scanned source holds no def of them. The
# scan reads the real names from the def it finds (rule building-allow-list-is-the-constant).
REFUSE_PARAMS = ("tool", "decision", "rule", "reason")  # guard_core.refuse()
ASK_PARAMS = ("rule", "reason")  # guard.ask_command()


def _callee(call, mod, reasons):
    """The def a refuse() or ask_command() call runs: `name(...)`, or `alias.name(...)` of an imported
    module. None when no module in the world defines it."""
    func = call.func
    if isinstance(func, ast.Name):
        found = reasons._function(func.id, mod)
    elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id in mod.module_alias:
        owner = reasons.world.get(mod.module_alias[func.value.id])
        found = reasons._function(func.attr, owner) if owner is not None else None
    else:
        found = None
    return found[1] if found else None


def _args_by_name(call, params):
    """-> {parameter: expression} for positional and keyword arguments. None when a `*` argument
    hides which parameter each value fills. A `**` argument names no rule or reason, so it is skipped."""
    if any(isinstance(a, ast.Starred) for a in call.args):
        return None
    named = dict(zip(params, call.args))
    named.update((k.arg, k.value) for k in call.keywords if k.arg)
    return named


def _refusals_of(call, locs, where, unattributed, mod, reasons):
    """-> [(refusal id, reason expression)] for one call that prints a refusal; [] for other calls.
    A call whose rule or reason the scan cannot name goes to `unattributed`. The positions of rule and
    reason come from the def the call runs."""
    name = _refusal_name(call, mod)
    if name not in ("refuse", "ask_command"):
        return []
    fdef = _callee(call, mod, reasons)
    if fdef is not None:
        params = tuple(a.arg for a in fdef.args.posonlyargs + fdef.args.args)
    else:
        params = REFUSE_PARAMS if name == "refuse" else ASK_PARAMS
    named = _args_by_name(call, params)
    if named is None or "rule" not in named or "reason" not in named:
        unattributed.append(where)
        return []
    rule, reason = named["rule"], named["reason"]
    if isinstance(rule, ast.Constant) and isinstance(rule.value, str):
        return [(rule.value, reason)]
    if name == "refuse" and isinstance(rule, ast.Name):
        bound = locs.get(rule.id, [])
        if any(isinstance(v, ast.Subscript) and isinstance(v.value, ast.Name) and v.value.id == PENDING_ASK
               for v, _, _ in bound):
            return []  # the ask_command() call sites carry these ids
        for value, slot, _ in bound:
            options = _tuple_options(value) if slot == 0 else None
            if options and all(len(t.elts) == 2 and isinstance(t.elts[0], ast.Constant) for t in options):
                return [(t.elts[0].value, t.elts[1]) for t in options]
    unattributed.append(where)
    return []


def _raw_refuse_reason(node):
    """The `permissionDecisionReason` expression of a dict literal that prints a refusal (`permissionDecision` "deny" or "ask"), else None.
    A dict whose decision is a variable is guard_core.refuse() itself, which the calls to it cover."""
    if not isinstance(node, ast.Dict):
        return None
    keys = {k.value: v for k, v in zip(node.keys, node.values) if isinstance(k, ast.Constant)}
    decision = keys.get("permissionDecision")
    if isinstance(decision, ast.Constant) and decision.value in ("deny", "ask"):
        return keys.get("permissionDecisionReason")
    return None


NO_REASON = object()  # a refuse print that names no reason: its site reads not resolved


def _item(target):
    """(name, key) of a `name["key"]` target with a string key, else None."""
    if isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name) \
            and isinstance(target.slice, ast.Constant) and isinstance(target.slice.value, str):
        return target.value.id, target.slice.value
    return None


def _key_value(scope, name, key):
    """The value `scope` first stores at `name["key"]`, NO_REASON when it stores none."""
    stored = [n for n in _own(scope) if isinstance(n, ast.Assign) and len(n.targets) == 1
              and _item(n.targets[0]) == (name, key)]
    return min(stored, key=lambda n: n.lineno).value if stored else NO_REASON


def _update_target(call):
    """The name `n` of an `n.update(...)` call, else None."""
    func = call.func if isinstance(call, ast.Call) else None
    if isinstance(func, ast.Attribute) and func.attr == "update" and isinstance(func.value, ast.Name):
        return func.value.id
    return None


def _pairs(node):
    """{key: value} of a dict literal's constant keys, or of a call's keyword arguments."""
    if isinstance(node, ast.Dict):
        return {k.value: v for k, v in zip(node.keys, node.values) if isinstance(k, ast.Constant)}
    return {k.arg: k.value for k in node.keywords if k.arg}


def _name_reaches(name, mod, scope, depth, returns=True):
    """True when a read of `name` in `scope` reaches the output (see _reaches_output). Memoized like it."""
    key = ("name", name, id(scope), depth, returns)
    if key not in mod.flow_memo:
        found = any(isinstance(n, ast.Name) and n.id == name and isinstance(n.ctx, ast.Load)
                    and _reaches_output(n, mod, scope, depth + 1, returns) for n in _own(scope))
        mod.flow_memo[key] = (found, scope)
    return mod.flow_memo[key][0]


def _bound_reaches(target, mod, scope, depth, returns=True):
    """True when a value bound to `target` reaches the output: a name, or an item of a name."""
    item = _item(target)
    if item is not None:
        return _name_reaches(item[0], mod, scope, depth, returns)
    return isinstance(target, ast.Name) and _name_reaches(target.id, mod, scope, depth, returns)


def _reaches_output(node, mod, scope, depth=0, returns=True):
    """True when the value of `node` reaches the output of `scope`: it is printed (`print(...)`, or a `json.dumps(...)`
    or `dict(...)` that is printed), returned, passed to `name.update(...)`, or bound to a name that reaches the
    output. An `name.update(...)` call reaches the output when its name does. A value that is an operand of `or`,
    `and` or a conditional expression reaches it as that expression does. `returns` false leaves out a return: a
    printing helper prints its parameter, and a parameter that is only returned is printed by no one. Memoized per
    (node, scope, depth, returns), so a name that is rebound many times is read once per depth, not once per path."""
    if depth > MAX_DEPTH:
        return False
    key = ("node", id(node), id(scope), depth, returns)
    if key not in mod.flow_memo:
        mod.flow_memo[key] = (_output_of(node, mod, scope, depth, returns), node, scope)
    return mod.flow_memo[key][0]


def _output_of(node, mod, scope, depth, returns):
    """The uncached read behind _reaches_output."""
    target = _update_target(node)
    if target is not None and _name_reaches(target, mod, scope, depth, returns):
        return True
    parent = mod.parents.get(id(node))
    if isinstance(parent, ast.BoolOp) or (isinstance(parent, ast.IfExp) and parent.test is not node):
        return _reaches_output(parent, mod, scope, depth + 1, returns)  # `p or {}`, `p if p else {}`: one of its values
    if isinstance(parent, ast.Return):
        return returns
    if isinstance(parent, ast.Call) and parent.func is not node:
        func = parent.func
        if isinstance(func, ast.Name) and func.id == "print":
            return True
        if (isinstance(func, ast.Attribute) and func.attr == "dumps") or (isinstance(func, ast.Name) and func.id == "dict"):
            return _reaches_output(parent, mod, scope, depth + 1, returns)
        target = _update_target(parent)
        return target is not None and _name_reaches(target, mod, scope, depth, returns)
    if isinstance(parent, ast.Assign) and parent.value is node:
        return any(_bound_reaches(t, mod, scope, depth, returns) for t in parent.targets)
    return False


def _refuse_print(node, scope, mod, locs, reasons):
    """The reason expression of a refuse print in `scope`, NO_REASON when it prints one with no reason, else None.
    A refuse print is a dict literal or a keyword call whose decision reads as "block" in some branch, or an
    `name["decision"] = ...` assignment that does, and whose value reaches the output of `scope`. A decision that
    cannot be read is no print, as in _raw_refuse_reason; so is a dict that nothing prints, such as one appended
    to a log."""
    item = _item(node.targets[0]) if isinstance(node, ast.Assign) and len(node.targets) == 1 else None
    if isinstance(node, (ast.Dict, ast.Call)):
        pairs = _pairs(node)
        decision, reason = pairs.get("decision"), pairs.get("reason", NO_REASON)
    elif item is not None and item[1] == "decision":
        decision, reason = node.value, _key_value(scope, item[0], "reason")
    else:
        return None
    if not _reads_block(decision, mod, locs, reasons):
        return None
    if isinstance(node, (ast.Dict, ast.Call)):
        reached = _reaches_output(node, mod, scope)
    else:
        reached = _name_reaches(item[0], mod, scope, 0)
    return reason if reached else None


def _reads_block(decision, mod, locs, reasons):
    """True when a decision expression reads as "block" in some branch: the one test of a block, for a refuse
    print and for a block dict a call passes to a printing helper."""
    return decision is not None and "block" in (reasons.alts(decision, mod, locs) or [])


def _is_dict_node(node):
    """A dict literal, or `dict(key=value, ...)` with keywords only: the two spellings of one dict."""
    return isinstance(node, ast.Dict) or (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                                          and node.func.id == "dict" and not node.args)


def _dict_options(expr):
    """The dict nodes a call's argument can be: the dict itself, or the dicts of an `A if c else B` branch."""
    if _is_dict_node(expr):
        return [expr]
    if isinstance(expr, ast.IfExp):
        return _dict_options(expr.body) + _dict_options(expr.orelse)
    return []


def _block_reason(node, mod, locs, reasons):
    """The reason expression of a dict node whose decision reads as "block", NO_REASON when it has no reason
    key, else None."""
    if not _is_dict_node(node):
        return None
    pairs = _pairs(node)
    if not _reads_block(pairs.get("decision"), mod, locs, reasons):
        return None
    return pairs.get("reason", NO_REASON)


def _base_name(base):
    """The class name a base expression names: `Stop`, or `stops.Stop` as `Stop`. None for any other base."""
    if isinstance(base, ast.Name):
        return base.id
    return base.attr if isinstance(base, ast.Attribute) else None


def _stop_classes(mod):
    """The names of the exception classes of a module that stops its run: `Stop` and each class that
    derives from one, by a plain or an attribute base. Empty when the module defines no `Stop`."""
    classes = [n for n in mod.tree.body if isinstance(n, ast.ClassDef)]
    names = {"Stop"} if any(c.name == "Stop" for c in classes) else set()
    grown = True
    while grown:
        grown = False
        for c in classes:
            if c.name not in names and any(_base_name(b) in names for b in c.bases):
                names.add(c.name)
                grown = True
    return names


def _kind_params(fdef, stops):
    """The parameters of `fdef` whose default is a Stop class, as `kind` in `def fail(why, kind=Stop)`: a
    `raise kind(...)` in that def raises a Stop. Empty when there is no def."""
    if fdef is None:
        return frozenset()
    args = fdef.args
    positional = args.posonlyargs + args.args
    pairs = list(zip(positional[len(positional) - len(args.defaults):], args.defaults))
    pairs += list(zip(args.kwonlyargs, args.kw_defaults))
    return frozenset(a.arg for a, d in pairs if isinstance(d, ast.Name) and d.id in stops)


def _stop_reason(node, stops, kinds=frozenset()):
    """The message expression of `raise Stop(...)` or `return Stop(...)`, also as `raise (A if c else B)(...)`,
    and as `raise kind(...)` for a name in `kinds` (see _kind_params). Else None."""
    call = node.exc if isinstance(node, ast.Raise) else node.value if isinstance(node, ast.Return) else None
    if not (isinstance(call, ast.Call) and call.args):
        return None
    func = call.func
    named = [n.id for n in ast.walk(func) if isinstance(n, ast.Name)] if isinstance(func, (ast.Name, ast.IfExp)) else []
    return call.args[0] if named and all(n in stops or n in kinds for n in named) else None


def _refusal_name(call, mod):
    """The name a call makes, read through `from guard_core import refuse as r`."""
    func = call.func
    if isinstance(func, ast.Name) and func.id in mod.from_names:
        return mod.from_names[func.id][1]
    return func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")


def _qualified_names(tree):
    """id(def) -> `Class.method` or `function`, for the site id of a refusal that names no rule."""
    names = {}

    def visit(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                visit(child, child.name + ".")
            elif isinstance(child, ast.FunctionDef):
                names[id(child)] = prefix + child.name
                visit(child, "")
            else:
                visit(child, prefix)
    visit(tree, "")
    return names


def _is_carried(expr, mod):
    """`str(e)` where `e` is a Stop caught by the except clause above it: its text was printed by its origin, a site of its own."""
    return (isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name) and expr.func.id == "str"
            and len(expr.args) == 1 and isinstance(expr.args[0], ast.Name)
            and _caught_as_stop(expr, expr.args[0].id, mod))


def _data_names(expr):
    """The names an expression reads as data. A call's arguments do not flow into its result as names: an
    argument is read where the call is made, so only the callee is descended."""
    stack, names = [expr], []
    while stack:
        node = stack.pop()
        if isinstance(node, ast.Name):
            names.append(node.id)
        elif isinstance(node, ast.Call):
            stack.append(node.func)
        else:
            stack.extend(ast.iter_child_nodes(node))
    return names


def _params_reaching(expr, params, locs, seen=frozenset()):
    """The parameters whose values reach `expr`, through the locals it reads. A local bound at run time
    (a loop target, a call's result) reaches none."""
    found = set()
    for name in _data_names(expr):
        if name in params:
            found.add(name)
        elif name in locs and name not in seen:
            for value, _, _ in locs[name]:
                if value is not None:
                    found |= _params_reaching(value, params, locs, seen | {name})
    return found


def _norm(text):
    return " ".join(text.split())


def _judge(texts, homes, fallback):
    """(status, spellings) for one refusal message. `texts` are its alternatives; None or [] reads no text,
    and `fallback` then spells the message. A "no cite" row spells each uncited alternative, normalized."""
    if not texts:
        return "not resolved", [fallback]
    bad = [t for t in texts if not cites(t, homes)]
    if not bad:
        return "cited", []
    return "no cite", [_norm(t) for t in bad]


def _dotted(node):
    """`a.b.c` as text for a chain of names and attributes, else None."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        inner = _dotted(node.value)
        return None if inner is None else inner + "." + node.attr
    return None


def _names_read_outside(world, owner):
    """The names of module `owner` that another module of the world reads: `from owner import name`, and
    `alias.name` where `alias` is `import owner` (`import owner.sub` makes the alias `owner.sub`). A def with
    one of these may be called where the reader does not look, so it is never a helper. An attribute of any
    other object is no read of the def."""
    names = set()
    for mod in world.values():
        if mod.name == owner:
            continue
        names.update(orig for src, orig in mod.from_names.values() if src == owner)
        aliases = {alias for alias, src in mod.module_alias.items() if src == owner}
        if aliases:
            names.update(n.attr for n in ast.walk(mod.tree)
                         if isinstance(n, ast.Attribute) and _dotted(n.value) in aliases)
    return names


class _Helpers:
    """The Stop helpers of one module, read from the code. A helper is a def, not a method, whose Stop message
    reaches one of its parameters, and whose every reference the reader can follow: a call of it, or a call's
    argument for a parameter that the callee only calls. The helper's own message is no site. Each call of it
    is one, read with the call's arguments. A parameter that a caller binds to a helper is called the same way."""

    def __init__(self, mod, reasons, unseen):
        self.mod, self.reasons = mod, reasons
        self.defs = [n for n in ast.walk(mod.tree) if isinstance(n, ast.FunctionDef)]
        self.own_defs = {id(d): {c.name: c for c in _own(d) if isinstance(c, ast.FunctionDef)} for d in self.defs}
        self.refs, self.hidden, self.binds = {}, set(), {}
        for name in {d.name for d in self.defs} & set(mod.name_loads):
            for ref in mod.name_loads[name]:
                self._reference(ref)
        self.helpers = {}
        for d in self.defs:
            if (self.refs.get(id(d)) and id(d) not in self.hidden and d.name not in unseen
                    and not isinstance(mod.parents.get(id(d)), ast.ClassDef) and self._reaches(d)):
                self.helpers[id(d)] = d
        self.printers = {}  # id(def) -> the parameters whose values its output prints
        candidates = [d for d in self.defs if self.refs.get(id(d)) and id(d) not in self.hidden
                      and d.name not in unseen and not isinstance(mod.parents.get(id(d)), ast.ClassDef)]
        grown = True
        while grown:  # a parameter passed on to a printer is printed too, so a pass can add names to another def
            grown = False
            for d in candidates:
                old = self.printers.get(id(d), frozenset())
                new = old | self._printed_params(d)
                if new != old:
                    self.printers[id(d)] = new
                    grown = True

    def lexical(self, name, node):
        """The def `name` refers to at `node`: the nearest enclosing def that binds it, else a module-level def."""
        cur = self.mod.parents.get(id(node))
        while cur is not None:
            if isinstance(cur, ast.FunctionDef):
                if name in self.own_defs[id(cur)]:
                    return self.own_defs[id(cur)][name]
                if name in self.reasons.locals_of(cur, self.mod):  # a variable of this def shadows an outer def
                    return None
            cur = self.mod.parents.get(id(cur))
        return self.mod.defs.get(name)

    def messages(self, d):
        """The message expressions that `d` prints in its own scope: the Stop messages it raises or returns, and the
        reasons of its refuse prints."""
        kinds = _kind_params(d, self.mod.stops)
        locs = self.reasons.locals_of(d, self.mod)
        stops = [m for node in _own(d) for m in (_stop_reason(node, self.mod.stops, kinds),) if m is not None]
        prints = [p for node in _own(d) for p in (_refuse_print(node, d, self.mod, locs, self.reasons),)
                  if isinstance(p, ast.AST)]
        return stops + prints

    def _reaches(self, d):
        params, locs = set(_param_names(d)), self.reasons.locals_of(d, self.mod)
        return any(_params_reaching(msg, params, locs) for msg in self.messages(d))

    def _called_only(self, callee, param):
        uses = [n for n in ast.walk(callee) if isinstance(n, ast.Name) and n.id == param]
        return bool(uses) and all(isinstance(self.mod.parents.get(id(n)), ast.Call)
                                  and self.mod.parents[id(n)].func is n for n in uses)

    def _reference(self, ref):
        """Classify one read of a name that may be a def: a call of it, or an argument that binds it to a
        parameter the callee only calls. Any other read hides the def from the reader."""
        target = self.lexical(ref.id, ref)
        if target is None:
            return
        parent = self.mod.parents.get(id(ref))
        call = self.mod.parents.get(id(parent)) if isinstance(parent, ast.keyword) else parent
        if isinstance(parent, ast.Call) and parent.func is ref:
            ok = True
        elif isinstance(call, ast.Call) and isinstance(call.func, ast.Name):
            callee = self.lexical(call.func.id, call)
            param = next((p for p, arg in _call_args(call, callee) if arg is ref), None) if callee else None
            ok = param is not None and self._called_only(callee, param)
            if ok:
                self.binds.setdefault((id(callee), param), {})[id(target)] = target
        else:
            ok = False
        if ok:
            self.refs[id(target)] = self.refs.get(id(target), 0) + 1
        else:
            self.hidden.add(id(target))

    def targets(self, call, fdef):
        """The helpers that a call prints a Stop of: the def it names, or the helpers a caller binds to the
        parameter it calls."""
        if not isinstance(call.func, ast.Name):
            return []
        lex = self.lexical(call.func.id, call)
        if lex is not None:
            return [lex] if id(lex) in self.helpers else []
        if fdef is None or call.func.id not in _param_names(fdef):
            return []
        return [h for h in self.binds.get((id(fdef), call.func.id), {}).values() if id(h) in self.helpers]

    def transparent(self, msg, fdef, locs):
        """A helper's own message that reaches its parameters: each call of the helper is read instead. `msg` is the
        Stop message or the reason of a refuse print at the site, and None or NO_REASON when there is none."""
        if fdef is None or id(fdef) not in self.helpers or not isinstance(msg, ast.AST):
            return False
        return bool(_params_reaching(msg, set(_param_names(fdef)), locs))

    def site(self, expr, locs, homes):
        """(status, spellings) for a message read at its own site."""
        if _is_carried(expr, self.mod):
            return "cited", []
        return _judge(self.reasons.alts(expr, self.mod, locs), homes, _unparse(expr))

    def printed_site(self, printed, site, locs, homes):
        """(status, spellings) for a refuse print's reason, read at its own site. A print with no reason is not resolved."""
        if printed is NO_REASON:
            return _judge([], homes, _unparse(site))
        return self.site(printed, locs, homes)

    def instance_rows(self, h, call, locs, homes):
        """(status, spellings) for each message of helper `h` that reaches its parameters, read with this call's
        arguments. An argument whose text is not read leaves that text unknown, and the message is judged on
        the text it has."""
        params = set(_param_names(h))
        hlocs = self.reasons.locals_of(h, self.mod)
        starred = any(isinstance(a, ast.Starred) for a in call.args) or any(k.arg is None for k in call.keywords)
        pairs = [] if starred else _call_args(call, h)
        rows = []
        for msg in self.messages(h):
            reach = _params_reaching(msg, params, hlocs)
            if not reach:
                continue
            if any(_is_carried(arg, self.mod) for name, arg in pairs if name in reach):
                rows.append(("cited", []))
                continue
            flocs, unknown = dict(hlocs), []
            for name, arg in pairs:
                texts = self.reasons.alts(arg, self.mod, locs)
                flocs[name] = [(_Fixed(texts), None, None)]
                if texts is None and name in reach:
                    unknown.append(arg)
            fallback = ", ".join(_unparse(a) for a in unknown) or _unparse(msg)
            rows.append(_judge(self.reasons.alts(msg, self.mod, flocs), homes, fallback))
        return rows

    def _printed_params(self, d):
        """The parameters of `d` that its output prints: a read of one that prints it, or a call that passes it to a
        parameter a printer prints. Only the argument counts, not a rebinding to another value (see _reads_argument)."""
        params = set(_param_names(d))
        locs = self.reasons.locals_of(d, self.mod)
        found = set()
        for node in _own(d):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id in params:
                if _reaches_output(node, self.mod, d, 0, returns=False) and self._reads_argument(node, node.id, d, locs):
                    found.add(node.id)
            elif isinstance(node, ast.Call) and not any(isinstance(a, ast.Starred) for a in node.args):
                g = self.printer(node)
                for name, arg in (_call_args(node, g) if g is not None else []):
                    if name in self.printers[id(g)] and isinstance(arg, ast.Name) and arg.id in params \
                            and self._reads_argument(arg, arg.id, d, locs):
                        found.add(arg.id)
        return frozenset(found)

    def _reads_argument(self, read, name, scope, locs):
        """True when a read of parameter `name` in `scope` sees its argument. A rebinding that runs on every path to the
        read hides the argument, unless its value names the argument (it derives from it). A rebinding in a branch or
        a loop that the read is not in hides nothing: the other path still holds the argument."""
        seen = _reaching(locs.get(name, []), read, self.mod)
        # `name[key] = ...` stores into the value the name holds: it rebinds nothing, so it is no rebinding.
        hiding = [value for value, _, at in seen if at is not None
                  and not (isinstance(at, ast.Assign) and all(isinstance(t, ast.Subscript) for t in at.targets))
                  and _runs_on_every_path(at, read, self.mod, scope)]
        return all(value is not None and name in {n.id for n in ast.walk(value) if isinstance(n, ast.Name)}
                   for value in hiding)

    def printer(self, call):
        """The printing def a call runs, read as the def the call's name refers to at the call; else None."""
        if not isinstance(call.func, ast.Name):
            return None
        d = self.lexical(call.func.id, call)
        return d if d is not None and id(d) in self.printers else None

    def print_rows(self, call, locs, homes):
        """(status, spellings) for each block dict that a call passes to a parameter its def prints. Each such
        dict is a refusal site of the caller: its reason is read at the call, in the caller's scope, as a refuse
        print's reason is. A dict that the call's argument holds only by a name is not read here."""
        d = self.printer(call)
        if d is None or any(isinstance(a, ast.Starred) for a in call.args):
            return []
        rows = []
        for name, arg in _call_args(call, d):
            if name not in self.printers[id(d)]:
                continue
            for dict_node in _dict_options(arg):
                reason = _block_reason(dict_node, self.mod, locs, self.reasons)
                if reason is not None:
                    rows.append(self.printed_site(reason, call, locs, homes))
        return rows


def _add(statuses, rid, where, status, spellings):
    statuses.setdefault(rid, []).append((where, status, spellings))


def refusal_status(sources, homes, scope, guards=None):
    """-> (statuses, unattributed). statuses: refusal id -> [(where, status, spellings)], where a `file:line`,
    status `cited`, `no cite` or `not resolved`, and spellings the normalized uncited texts (or the unread
    expression) that an exempt key's prefix must start. `sources` maps each module name to its text; `scope`
    names the modules whose refusals count, and `guards` the guard modules among them (all of `scope` when
    None). A guard module's refuse() and ask_command() calls name their id. Any module in scope also counts a
    raw refusal dict, a refuse print (see _refuse_print), a `raise Stop(...)`, `return Stop(...)` or
    `raise kind(...)` (see _kind_params) of its own, each call of a helper, and each block dict a call passes to a
    printing helper (see _Helpers.print_rows); their id is
    `module:function`, the function that makes the refusal. A helper's own message is no site, and a hook that
    is no guard module (a judge hook) prints its refusal in its own refuse(), so only that print counts there.
    unattributed: the calls whose id the scan cannot read."""
    world = {name: _Module(name, text) for name, text in sources.items()}
    reasons = _Reasons(world)
    statuses, unattributed = {}, []
    guards = scope if guards is None else guards
    for mod in world.values():
        if mod.name not in scope:
            continue
        qualified = _qualified_names(mod.tree)
        helpers = _Helpers(mod, reasons, _names_read_outside(world, mod.name))
        scopes = [(mod.tree, {}, "<module>", None)] + [(n, reasons.locals_of(n, mod), qualified.get(id(n), n.name), n)
                                                       for n in ast.walk(mod.tree) if isinstance(n, ast.FunctionDef)]
        for node, locs, func, fdef in scopes:
            rid = "%s:%s" % (mod.name, func)
            for site in _own(node):
                where = "%s.py:%d" % (mod.name, site.lineno) if hasattr(site, "lineno") else ""
                printed = _refuse_print(site, node, mod, locs, reasons)
                if printed is not None and not helpers.transparent(printed, fdef, locs):
                    _add(statuses, rid, where, *helpers.printed_site(printed, site, locs, homes))
                if isinstance(site, ast.Call):
                    if mod.name in guards:
                        for ref, expr in _refusals_of(site, locs, where, unattributed, mod, reasons):
                            _add(statuses, ref, where, *helpers.site(expr, locs, homes))
                    for h in helpers.targets(site, fdef):
                        for status, spellings in helpers.instance_rows(h, site, locs, homes):
                            _add(statuses, rid, where, status, spellings)
                    for status, spellings in helpers.print_rows(site, locs, homes):
                        _add(statuses, rid, where, status, spellings)
                    continue
                stop = _stop_reason(site, mod.stops, _kind_params(fdef, mod.stops))
                expr = _raw_refuse_reason(site) or stop
                if expr is not None and not helpers.transparent(stop, fdef, locs):
                    _add(statuses, rid, where, *helpers.site(expr, locs, homes))
    for rows in statuses.values():
        rows.sort(key=lambda row: (row[0].rsplit(":", 1)[0], int(row[0].rsplit(":", 1)[1])))
    return statuses, unattributed


def _home_reason(value):
    """(home, reason, sites) of an exempt entry. A bare home names no reason and one site. A tuple gives
    (home, reason), or (home, reason, sites) when one key names several identical sites."""
    if not isinstance(value, tuple):
        return value, None, 1
    return value[0], (value[1] if len(value) > 1 else None), (value[2] if len(value) > 2 else 1)


def refusal_problems(sources, homes, exempt, scope, emitted=None, guards=None):
    """The ratchet's problems, one line each. Empty when every refusal id cites or is exempt.

    An exempt key is `rule id`, whole, for a guard rule, or `module:function: text prefix` for a function.
    Each uncited spelling of a function belongs to the longest prefix that starts it, so a key names the sites
    it was written for: a new uncited site with other text, or a copy of a key, makes the count wrong. An
    entry that names a prefix carries its reason, and a count of sites when several identical ones share it."""
    statuses, unattributed = refusal_status(sources, homes, scope, guards)
    problems = ["%s: refuse() or ask_command() id is not a string literal the scan can read" % w
                for w in unattributed]
    if emitted is not None:
        problems += ["%s: refusal id is not in rule_audit.emitted_rule_ids" % rid
                     for rid in sorted(r for r in set(statuses) - emitted if ":" not in r)]  # `module:function` ids are no guard.log ids
    rows = {rid: [row for row in found if row[1] != "cited"] for rid, found in statuses.items()}
    rows = {rid: found for rid, found in rows.items() if found}
    keys = {}
    for key in exempt:
        rid, sep, prefix = key.partition(": ")
        keys[key] = (rid, prefix if sep else None)
    whole = {rid for rid, prefix in keys.values() if prefix is None and ":" not in rid}
    chosen, bad = {}, {}  # key -> sites it names; rid -> rows with a spelling no key names
    for rid in sorted(rows):
        if rid in whole:
            continue
        for where, status, spellings in rows[rid]:
            picks, unnamed = set(), False
            for spelling in spellings:
                best = max(((len(prefix), key) for key, (krid, prefix) in keys.items()
                            if krid == rid and prefix is not None and _norm(spelling).startswith(prefix)), default=None)
                if best is None:
                    unnamed = True
                else:
                    picks.add(best[1])
            for key in picks:
                chosen[key] = chosen.get(key, 0) + 1
            if unnamed:
                bad.setdefault(rid, []).append("%s %s" % (where, status))
    for key in sorted(exempt):
        rid, prefix = keys[key]
        home, reason, sites = _home_reason(exempt[key])
        if prefix is None:
            if ":" in rid:
                problems.append("%s: a function id needs a text prefix: `%s: <text>`" % (key, rid))
            if rid not in statuses:
                problems.append("%s: remove from exempt; no refusal prints it" % key)
            elif rid not in rows:
                problems.append("%s: remove from exempt; every site now cites" % key)
        else:
            if rid not in statuses:
                problems.append("%s: remove from exempt; no refusal prints it" % key)
            elif not chosen.get(key):
                problems.append("%s: remove from exempt; no uncited site starts with `%s`" % (key, prefix))
            elif chosen[key] != sites:
                problems.append("%s: matches %d sites; the key names %d" % (key, chosen[key], sites))
            if not reason or len(reason.split()) < EXEMPT_REASON_WORDS:
                problems.append("%s: needs a reason of at least %d words" % (key, EXEMPT_REASON_WORDS))
        if not HOME_RE.fullmatch(home):
            problems.append("%s: exempt home `%s` is not a step slug or debt id" % (key, home))
    for rid in sorted(bad):
        problems.append("%s: %s" % (rid, "; ".join(bad[rid])))
    return problems


CONFIG_DIR_SCRIPT_RE = re.compile(
    r"(?:\$\{CLAUDE_CONFIG_DIR(?::-\$HOME/\.claude)?\}|\$CLAUDE_CONFIG_DIR|~/\.claude|\$\{?HOME\}?/\.claude)"
    r"/([A-Za-z0-9_./-]+\.py)")  # a script under the config dir, which is this repo's root
REPO_SCRIPT_RE = re.compile(r"(?<![\w./-])((?:hooks|lint|merge|janitor)/[A-Za-z0-9_./-]+\.py)")  # a repo-relative path


def settings_scripts(root=rule_audit.ROOT):
    """The repo-relative .py scripts that the hook commands in settings.json run. A command names its script under
    the config dir (`${CLAUDE_CONFIG_DIR:-$HOME/.claude}/<path>`, `~/.claude/<path>` or `$HOME/.claude/<path>`), and
    <path> is the same path in this repo; or it names it by that repo-relative path."""
    with open(os.path.join(root, "settings.json"), encoding="utf-8") as f:
        settings = json.load(f)
    found = set()

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "command" and isinstance(value, str):
                    found.update(CONFIG_DIR_SCRIPT_RE.findall(value))
                    found.update(REPO_SCRIPT_RE.findall(value))
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(settings)
    return sorted(found)


def _hooks_world():
    """The text of every hooks module but the tests, the merge tool, and each .py script that settings.json wires
    (lint/report_guard.py, janitor/*.py). The scan reads all of them, so a judge hook or a new module that prints a
    refusal is in scope with no list of its own."""
    root = rule_audit.ROOT
    paths = glob.glob(os.path.join(root, "hooks", "*.py")) + [os.path.join(root, "merge", "merge.py")]
    paths += [os.path.join(root, rel) for rel in settings_scripts(root)]
    return {os.path.splitext(os.path.basename(p))[0]: rule_audit.read(p)
            for p in paths if not os.path.basename(p).startswith("test_")}


def _guard_names():
    """The guard modules, by the same glob as rule_audit.guard_paths: their refuse() and ask_command()
    calls are sites. Other modules count only their own raw refusal dicts and `raise Stop(...)`."""
    return {os.path.splitext(os.path.basename(p))[0] for p in rule_audit.guard_paths(rule_audit.ROOT)}


class RefusalCiteRepoTests(unittest.TestCase):
    """The ratchet, run on this repo as it is now."""

    def test_every_guard_refusal_prints_a_cite_or_is_exempt(self):
        world = _hooks_world()
        problems = refusal_problems(world, cite_homes(), REFUSAL_UNCITED_EXEMPT, set(world),
                                    rule_audit.emitted_rule_ids(rule_audit.ROOT), guards=_guard_names())
        self.assertEqual(problems, [], "\n".join(problems))

    def test_the_repo_scope_reads_the_judge_hooks_and_the_merge_tool(self):
        self.assertLessEqual({"blind_brief", "call_judge", "prose_judge", "sendmessage_state", "merge"},
                             set(_hooks_world()))

    def test_settings_wires_the_scripts_outside_hooks(self):
        wired = settings_scripts()
        self.assertIn("lint/report_guard.py", wired)
        self.assertIn("janitor/agent_end_reap.py", wired)
        self.assertIn("janitor/session_end_sweep.py", wired)

    def test_every_script_settings_wires_exists(self):
        self.assertTrue(settings_scripts(), "settings.json wires no .py script, so the scope is unknown")
        gone = [rel for rel in settings_scripts() if not os.path.isfile(os.path.join(rule_audit.ROOT, rel))]
        self.assertEqual(gone, [], "wired but missing: " + ", ".join(gone))

    def test_every_script_settings_wires_is_in_the_scanned_world(self):
        wired = settings_scripts()
        self.assertTrue(wired, "settings.json wires no .py script, so the scope is unknown")
        world = _hooks_world()
        missing = [rel for rel in wired if os.path.splitext(os.path.basename(rel))[0] not in world]
        self.assertEqual(missing, [], "wired by settings.json but not scanned: " + ", ".join(missing))

    def test_cite_homes_reads_the_style_file_anchors(self):
        decisions, anchors = cite_homes()
        self.assertIn("owner-override", decisions)
        self.assertIn("outcomes-tests-are-statements", anchors)  # CLAUDE.md
        self.assertIn("style-cut-narration", anchors)  # output-styles/shiv-stylisms.md

    # Ids whose rewrites take them off the exempt list.
    LEAVE_EXEMPT = {"builder-test-edit", "detached-launch", "git-env-set", "lane-by-slug", "load-brake",
                    "bare-merge", "cite-by-id", "ask-alone", "linked-node-modules", "owner-judge",
                    "item-field-rendered", "page-stale", "agent-model-cap"}
    # Ids that stay exempt, each with its home.
    STAY_EXEMPT = {"gh-login-switch", "handoff-unread", "merge-role-proof", "option-letter-keys",
                   "question-departs", "rework-off-page", "trust-card-in-build"}

    def test_the_rewritten_ids_leave_the_exempt_list_and_the_kept_ids_keep_a_home(self):
        still = sorted(self.LEAVE_EXEMPT & set(REFUSAL_UNCITED_EXEMPT))
        self.assertEqual(still, [], "still exempt: " + ", ".join(still))
        for rid in sorted(self.STAY_EXEMPT):
            with self.subTest(rid=rid):
                self.assertIn(rid, REFUSAL_UNCITED_EXEMPT)
                home, reason, _ = _home_reason(REFUSAL_UNCITED_EXEMPT[rid])
                self.assertTrue(HOME_RE.fullmatch(home))
                self.assertGreaterEqual(len((reason or "").split()), EXEMPT_REASON_WORDS, rid)


HOMES = ({"alpha"}, {"anchor-one"})
SCOPE = {"guard"}


def status_of(src, rid, extra=None, homes=HOMES, module="guard"):
    sources = dict(extra or {}, **{module: src})
    statuses, _ = refusal_status(sources, homes, {module})
    return [s for _, s, _ in statuses.get(rid, [])]


def unattributed_of(src):
    return refusal_status({"guard": src}, HOMES, SCOPE)[1]


def site_problems(module, src):
    """The ratchet's problems for one module's source, with no exempt list and no emitted check."""
    return refusal_problems({module: src}, HOMES, {}, {module})


def module_problems(src, exempt, module="merge"):
    """The ratchet's problems for one module's source, with `exempt` as the exempt list."""
    return refusal_problems({module: src}, HOMES, exempt, {module})


def uncited_site(problems, module):
    """True when a problem names a site in `module` whose reason prints no cite."""
    return any("%s.py:" % module in p and "no cite" in p for p in problems)


CRASH_REASON = ("guard-crash: the guard is missing a part and cannot judge this call.\n"
                "Remedy: reinstall, don't retry # or /* or // here.")


def raw_refuse_src(reason):
    """A JSON refusal printed straight to stdout: the shape of the guard-crash refusal in hooks/guard.py."""
    return ('def crash():\n'
            '    print(json.dumps({"hookSpecificOutput": {\n'
            '        "hookEventName": "PreToolUse", "permissionDecision": "deny",\n'
            '        "permissionDecisionReason": """%s"""}}))\n'
            '    sys.exit(0)\n' % reason)


JUDGE_SHAPES = (("blind_brief", "    sys.exit(0)"), ("call_judge", "    return 0"),
                ("prose_judge", "    return 0"), ("sendmessage_state", "    return 0"))


def judge_src(prefix, exit_line, fallback=None):
    """A judge hook's refuse(): a constant prefix, an optional fallback reason, then a JSON refusal printed
    with exit 0. The shape of hooks/blind_brief.py, call_judge.py, prose_judge.py and sendmessage_state.py."""
    lines = ['PREFIX = "%s"' % prefix, "def refuse(payload, tool, reason):"]
    if fallback:
        lines.append('    reason = reason or "%s"' % fallback)
    lines += ['    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",',
              '                                             "permissionDecision": "deny",',
              '                                             "permissionDecisionReason": PREFIX + reason}}))',
              exit_line]
    return "\n".join(lines) + "\n"


def merge_src(raise_line, defs="", body=None):
    """The stop classes of merge/merge.py, then `defs`, then one function `go(b)` that runs `raise_line`,
    or the lines of `body` when it is given."""
    lines = body if body is not None else "    %s\n" % raise_line
    return ('class Stop(Exception):\n    """A refusal."""\n'
            'class NetStop(Stop):\n    """A network error."""\n'
            'class Dropped(Stop):\n    """A dropped line."""\n'
            'class Held(Stop):\n    pass\n'
            'LOCK_CITE = "(decision alpha, one run holds the merge lock)"\n'
            + defs + 'def go(b):\n' + lines)


BRANCH_HELPER = ('def helper(seg):\n'
                 '    if seg:\n'
                 '        return seg, "see decision alpha"\n'
                 '    return "", ""\n')
BRANCH_PICK = 'def pick(seg):\n    return seg\n'  # its reason is a parameter, so the text is known only at run time


def branch_src(judge_body):
    """A guard module with a cited helper, a run-time helper, and `judge(seg, tool)` made of the lines of `judge_body`."""
    return BRANCH_HELPER + BRANCH_PICK + 'def judge(seg, tool):\n' + judge_body


class RefusalCiteFixtureTests(unittest.TestCase):
    """The cite pattern and the scanner, on in-memory source."""

    def test_a_decision_slug_that_exists_cites(self):
        self.assertEqual(status_of('refuse(t, "deny", "r1", "see decision alpha", m)', "r1"), ["cited"])

    def test_a_decision_slug_that_is_missing_does_not_cite(self):
        self.assertEqual(status_of('refuse(t, "deny", "r1", "see decision beta", m)', "r1"), ["no cite"])

    def test_a_rule_anchor_that_exists_cites_and_a_missing_one_does_not(self):
        self.assertEqual(status_of('refuse(t, "deny", "r1", "rule anchor-one holds", m)', "r1"), ["cited"])
        self.assertEqual(status_of('refuse(t, "deny", "r1", "rule anchor-two holds", m)', "r1"), ["no cite"])

    def test_the_cite_word_must_stand_alone(self):
        self.assertEqual(status_of('refuse(t, "deny", "r1", "undecision alpha", m)', "r1"), ["no cite"])

    def test_a_hash_inside_a_reason_string_is_text_not_a_comment(self):
        src = 'refuse(t, "deny", "hash-id", "use the # sign, see decision alpha", m)\n'
        self.assertEqual(status_of(src, "hash-id"), ["cited"])

    def test_a_commented_out_refusal_is_no_site(self):
        src = '# refuse(t, "deny", "ghost", "see decision alpha", m)\n'
        self.assertEqual(status_of(src, "ghost"), [])

    def test_a_multi_line_reason_that_cites_is_read(self):
        src = 'refuse(t, "deny", "multi", """first line\nsecond line, see decision alpha""", m)\n'
        self.assertEqual(status_of(src, "multi"), ["cited"])

    def test_a_lone_quote_in_text_is_no_cite_and_no_parse_error(self):
        src = 'refuse(t, "deny", "quote", "Don\'t refuse this act", m)\n'
        self.assertEqual(status_of(src, "quote"), ["no cite"])

    def test_a_record_only_id_is_not_a_refusal(self):
        self.assertEqual(status_of('record(t, "noted", "note-only", m)\n', "note-only"), [])

    def test_a_module_constant_with_a_cite_passes(self):
        src = 'REASON = "held, see decision alpha"\nrefuse(t, "deny", "const-id", REASON, m)\n'
        self.assertEqual(status_of(src, "const-id"), ["cited"])

    def test_a_function_reason_needs_every_return_to_cite(self):
        src = ('def why(x):\n'
               '    if x:\n'
               '        return "see decision alpha"\n'
               '    return "no citation here"\n'
               'refuse(t, "deny", "fn-id", why(1), m)\n')
        self.assertEqual(status_of(src, "fn-id"), ["no cite"])

    def test_an_imported_constant_is_followed_into_its_module(self):
        core = 'HELD = "held, see decision alpha"\n'
        src = 'def go():\n    from guard_core import HELD\n    refuse(t, "deny", "imp-id", HELD, m)\n'
        self.assertEqual(status_of(src, "imp-id", extra={"guard_core": core}), ["cited"])

    def test_a_format_call_and_a_conditional_both_read(self):
        src = ('A = "one {x}, see decision alpha"\nB = "two {x}"\n'
               'def go(c):\n'
               '    reason = (A if c else B)\n'
               '    refuse(t, "deny", "fmt-id", reason.format(x=1), m)\n')
        self.assertEqual(status_of(src, "fmt-id"), ["no cite"])

    def test_a_reason_passed_in_as_an_argument_is_not_resolved(self):
        src = 'def go(reason):\n    refuse(t, "deny", "param-id", reason, m)\n'
        self.assertEqual(status_of(src, "param-id"), ["not resolved"])

    def test_one_uncited_site_fails_an_id_with_a_cited_site(self):
        src = ('refuse(t, "deny", "two-sites", "see decision alpha", m)\n'
               'refuse(t, "deny", "two-sites", "no cite", m)\n')
        self.assertEqual(status_of(src, "two-sites"), ["cited", "no cite"])

    def test_a_table_of_codes_gives_each_code_its_own_reason(self):
        src = ('def go(role):\n'
               '    code, why = {"a": ("tbl-one", "see decision alpha")}.get(role, ("tbl-two", "no cite"))\n'
               '    refuse(t, "deny", code, why, m)\n')
        self.assertEqual(status_of(src, "tbl-one"), ["cited"])
        self.assertEqual(status_of(src, "tbl-two"), ["no cite"])

    def test_an_ask_command_call_is_a_site(self):
        src = 'ask_command("ask-id", "see decision alpha", m, "cmd")\n'
        self.assertEqual(status_of(src, "ask-id"), ["cited"])

    def test_the_pending_ask_rule_is_covered_by_the_ask_command_sites(self):
        src = ('def flush():\n'
               '    rule, reason, matched, command = PENDING_ASK[0]\n'
               '    refuse(t, "ask", rule, reason, matched)\n')
        _, unattributed = refusal_status({"guard": src}, HOMES, SCOPE)
        self.assertEqual(unattributed, [])

    def test_a_variable_rule_outside_a_table_is_unattributed(self):
        src = 'def go(rule):\n    refuse(t, "deny", rule, "see decision alpha", m)\n'
        _, unattributed = refusal_status({"guard": src}, HOMES, SCOPE)
        self.assertEqual(unattributed, ["guard.py:2"])

    def test_a_module_outside_the_scope_is_not_scanned(self):
        src = 'refuse(t, "deny", "blind-id", "no cite", m)\n'
        statuses, _ = refusal_status({"blind_brief": src}, HOMES, SCOPE)
        self.assertEqual(statuses, {})

    def test_a_falsy_branch_is_no_reason_and_the_live_branch_cites(self):
        src = ('def why(x):\n'
               '    if x:\n'
               '        return "see decision alpha"\n'
               '    return ""\n'
               'refuse(t, "deny", "dead-id", why(1), m)\n')
        self.assertEqual(status_of(src, "dead-id"), ["cited"])

    def test_an_element_of_a_tuple_a_call_returns_is_read(self):
        src = ('def hit(x):\n'
               '    if x:\n'
               '        return "see decision alpha", x\n'
               '    return None\n'
               'def go(x):\n'
               '    behind = hit(x)\n'
               '    if behind:\n'
               '        refuse(t, "deny", "tuple-id", behind[0], behind[1])\n')
        self.assertEqual(status_of(src, "tuple-id"), ["cited"])
        uncited = src.replace("see decision alpha", "no cite here")
        self.assertEqual(status_of(uncited, "tuple-id"), ["no cite"])

    def test_a_run_time_walrus_in_another_branch_does_not_unresolve_a_cited_branch(self):
        src = branch_src('    if seg == "a":\n'
                         '        hit = helper(seg)\n'
                         '        if hit[0]:\n'
                         '            refuse(tool, "deny", "walrus-id", hit[1], hit[0])\n'
                         '    elif seg == "b" and (hit := pick(seg)):\n'
                         '        return hit\n'
                         '    return None\n')
        self.assertEqual(status_of(src, "walrus-id"), ["cited"],
                         "a run-time walrus of hit in another branch hides the cited hit this branch binds")

    def test_an_unbound_read_in_a_branch_stays_not_resolved(self):
        src = branch_src('    if seg == "a":\n'
                         '        refuse(tool, "deny", "unbound-id", hit[1], hit[0])\n'
                         '    elif seg == "b":\n'
                         '        hit = pick(seg)\n'
                         '        return hit\n'
                         '    return None\n')
        self.assertEqual(status_of(src, "unbound-id"), ["not resolved"],
                         "no binding of hit reaches this refusal, so its reason must not resolve")

    def test_a_cited_binding_in_a_sibling_branch_does_not_reach_a_refusal(self):
        src = branch_src('    if seg == "a":\n'
                         '        hit = helper(seg)\n'
                         '        return hit\n'
                         '    elif seg == "b":\n'
                         '        refuse(tool, "deny", "sibling-id", hit[1], hit[0])\n'
                         '    return None\n')
        self.assertEqual(status_of(src, "sibling-id"), ["not resolved"],
                         "the cited hit is bound in a sibling branch, which does not reach this refusal")

    def test_a_branch_whose_only_reaching_binding_is_run_time_stays_not_resolved(self):
        src = branch_src('    if seg == "a":\n'
                         '        hit = helper(seg)\n'
                         '        return hit\n'
                         '    elif seg == "b":\n'
                         '        hit = pick(seg)\n'
                         '        if hit[0]:\n'
                         '            refuse(tool, "deny", "runtime-id", hit[1], hit[0])\n'
                         '    return None\n')
        self.assertEqual(status_of(src, "runtime-id"), ["not resolved"],
                         "the only binding reaching this refusal is run-time; a cited binding elsewhere must not resolve it")

    def test_a_single_binding_read_in_its_branch_stays_cited(self):
        src = branch_src('    if seg == "a":\n'
                         '        hit = helper(seg)\n'
                         '        if hit[0]:\n'
                         '            refuse(tool, "deny", "single-id", hit[1], hit[0])\n'
                         '    return None\n')
        self.assertEqual(status_of(src, "single-id"), ["cited"])

    def test_a_later_run_time_walrus_does_not_unresolve_an_earlier_cited_read(self):
        src = branch_src('    if seg == "a":\n'
                         '        hit = helper(seg)\n'
                         '        if hit:\n'
                         '            refuse(tool, "deny", "later-walrus-id", hit[1], hit[0])\n'
                         '    if seg == "b" and (hit := pick(seg)):\n'
                         '        return hit\n'
                         '    return None\n')
        self.assertEqual(status_of(src, "later-walrus-id"), ["cited"],
                         "a walrus in a later if runs after the read, so it must not pool into the read")

    def test_a_run_time_binding_before_the_read_stays_not_resolved(self):
        src = branch_src('    hit = pick(seg)\n'
                         '    if seg == "a":\n'
                         '        hit = helper(seg)\n'
                         '    if hit[0]:\n'
                         '        refuse(tool, "deny", "before-id", hit[1], hit[0])\n'
                         '    return None\n')
        self.assertEqual(status_of(src, "before-id"), ["not resolved"],
                         "the run-time binding before the read reaches it when seg is not a, so it stays unresolved")

    def test_a_loop_rebinding_after_the_read_stays_not_resolved(self):
        src = branch_src('    hit = helper(seg)\n'
                         '    for x in seg:\n'
                         '        if x:\n'
                         '            refuse(tool, "deny", "loop-id", hit[1], hit[0])\n'
                         '        hit = pick(x)\n'
                         '    return None\n')
        self.assertEqual(status_of(src, "loop-id"), ["not resolved"],
                         "the run-time rebinding after the read reaches it when the loop re-enters")

    def test_a_run_time_walrus_in_a_conditional_test_reaches_the_read_before_it(self):
        src = branch_src('    hit = helper(seg)\n'
                         '    refuse(tool, "deny", "cond-id", hit[1] if (hit := pick(seg)) else "", hit[0])\n'
                         '    return None\n')
        self.assertEqual(status_of(src, "cond-id"), ["not resolved"],
                         "a conditional runs its test before its body, so the walrus in the test reaches hit[1]")

    def test_a_run_time_walrus_in_a_comprehension_if_reaches_its_element(self):
        src = branch_src('    hit = helper(seg)\n'
                         '    return [refuse(tool, "deny", "comp-id", hit[1], hit[0])\n'
                         '            for x in seg if (hit := pick(x))]\n')
        self.assertEqual(status_of(src, "comp-id"), ["not resolved"],
                         "a comprehension's if runs before its element, so the walrus in the if reaches the element")

    def test_a_while_test_reads_a_run_time_rebind_in_the_body(self):
        src = branch_src('    hit = helper(seg)\n'
                         '    while refuse(tool, "deny", "while-id", hit[1], hit[0]) or pick(seg):\n'
                         '        hit = pick(seg)\n'
                         '    return None\n')
        self.assertEqual(status_of(src, "while-id"), ["not resolved"],
                         "the body rebinds hit before the test runs again, so the test's read is not resolved")

    def test_a_lambda_called_after_a_run_time_rebind_stays_not_resolved(self):
        src = branch_src('    hit = helper(seg)\n'
                         '    later = lambda: refuse(tool, "deny", "lambda-id", hit[1], hit[0])\n'
                         '    hit = pick(seg)\n'
                         '    return later()\n')
        self.assertEqual(status_of(src, "lambda-id"), ["not resolved"],
                         "the lambda runs after the rebind, so the read it makes is of the run-time hit")

    def test_a_lambda_defined_after_a_run_time_rebind_stays_not_resolved(self):
        src = branch_src('    hit = helper(seg)\n'
                         '    hit = pick(seg)\n'
                         '    later = lambda: refuse(tool, "deny", "lambda-guard", hit[1], hit[0])\n'
                         '    return later()\n')
        self.assertEqual(status_of(src, "lambda-guard"), ["not resolved"],
                         "the run-time rebind comes before the lambda, so the read is of the run-time hit")

    def test_a_generator_read_after_a_run_time_rebind_stays_not_resolved(self):
        src = branch_src('    hit = helper(seg)\n'
                         '    g = (refuse(tool, "deny", "p-id", hit[1], hit[0]) for x in seg)\n'
                         '    hit = pick(seg)\n'
                         '    return next(g)\n')
        self.assertEqual(status_of(src, "p-id"), ["not resolved"],
                         "a generator expression runs when next() pulls it, after the rebind, so its read is run-time")

    def test_a_generator_read_after_a_rebind_in_an_if_stays_not_resolved(self):
        src = branch_src('    hit = helper(seg)\n'
                         '    g = (refuse(tool, "deny", "p-id2", hit[1], hit[0]) for x in seg)\n'
                         '    if seg:\n'
                         '        hit = pick(seg)\n'
                         '    return list(g)\n')
        self.assertEqual(status_of(src, "p-id2"), ["not resolved"],
                         "the if may rebind hit before list() pulls the generator, so its read is run-time")

    def test_an_eager_generator_read_with_no_rebind_stays_cited(self):
        src = branch_src('    hit = helper(seg)\n'
                         '    return any(refuse(tool, "deny", "eager-id", hit[1], hit[0]) for x in seg)\n')
        self.assertEqual(status_of(src, "eager-id"), ["cited"])

    def test_an_empty_reason_is_not_resolved(self):
        self.assertEqual(status_of('refuse(t, "deny", "empty-id", "", m)\n', "empty-id"), ["not resolved"])

    def test_a_percent_format_keeps_the_static_text(self):
        src = 'REASON = "held by %s, see decision alpha"\nrefuse(t, "deny", "pct-id", REASON % "x", m)\n'
        self.assertEqual(status_of(src, "pct-id"), ["cited"])

    def test_a_run_time_piece_in_a_join_keeps_the_static_text_only(self):
        cited = 'def go(x):\n    refuse(t, "deny", "join-id", "see decision alpha " + x, m)\n'
        uncited = 'def go(x):\n    refuse(t, "deny", "join-id", "no cite " + x, m)\n'
        self.assertEqual(status_of(cited, "join-id"), ["cited"])
        self.assertEqual(status_of(uncited, "join-id"), ["no cite"])

    def test_a_keyword_rule_and_reason_are_read_as_a_site(self):
        cited = 'refuse(t, "deny", rule="kw-id", reason="see decision alpha", matched=m)\n'
        uncited = 'refuse(t, "deny", rule="kw-id", reason="no cite", matched=m)\n'
        self.assertEqual(status_of(cited, "kw-id"), ["cited"])
        self.assertEqual(status_of(uncited, "kw-id"), ["no cite"])

    def test_a_keyword_ask_command_is_a_site(self):
        src = 'ask_command(rule="kw-ask", reason="see decision alpha", matched=m, command="cmd")\n'
        self.assertEqual(status_of(src, "kw-ask"), ["cited"])

    def test_a_keyword_reason_that_is_a_parameter_is_not_resolved(self):
        src = 'def go(reason):\n    refuse(t, "deny", rule="kw-param", reason=reason, matched=m)\n'
        self.assertEqual(status_of(src, "kw-param"), ["not resolved"])

    def test_a_keyword_rule_that_is_a_variable_is_unattributed(self):
        src = 'def go(rule):\n    refuse(t, "deny", rule=rule, reason="see decision alpha", matched=m)\n'
        self.assertEqual(unattributed_of(src), ["guard.py:2"])
        src = 'def go(rule):\n    ask_command(rule=rule, reason="see decision alpha", matched=m, command="c")\n'
        self.assertEqual(unattributed_of(src), ["guard.py:2"])

    def test_a_call_that_hides_its_rule_or_reason_is_unattributed(self):
        for call in ('refuse(*parts)', 'refuse(t, "deny", **kw)', 'ask_command(*parts)',
                     'refuse(t, "deny", "two-args")', 'refuse(t, "deny", rule="no-reason", matched=m)'):
            with self.subTest(call=call):
                self.assertEqual(unattributed_of("def go():\n    %s\n" % call), ["guard.py:2"])

    def test_a_raw_refuse_printed_outside_refuse_needs_a_cite(self):
        problems = site_problems("guard", raw_refuse_src(CRASH_REASON))
        self.assertTrue(uncited_site(problems, "guard"), problems)
        cited = raw_refuse_src(CRASH_REASON + " See decision alpha.")
        self.assertEqual(site_problems("guard", cited), [])

    def test_a_refuse_call_outside_a_guard_module_is_no_site(self):
        call = 'refuse(t, "deny", "call-id", "no cite", m)\n'
        statuses, _ = refusal_status({"judge": call}, HOMES, {"judge"}, guards=set())
        self.assertEqual(statuses, {})
        statuses, _ = refusal_status({"judge": call}, HOMES, {"judge"}, guards={"judge"})
        self.assertEqual([s for _, s, _ in statuses["call-id"]], ["no cite"])

    def test_a_judge_refuse_reads_its_fallback_and_its_cite_prefix(self):
        fallback = "the receiver must hear only what changes its work, don't # or /* or //."
        for module, exit_line in JUDGE_SHAPES:
            with self.subTest(module=module):
                problems = site_problems(module, judge_src("rule anchor-one: ", exit_line, fallback))
                self.assertTrue(uncited_site(problems, module), problems)
                self.assertEqual(site_problems(module, judge_src("rule anchor-one: ", exit_line)), [])
                cited = judge_src("rule anchor-one: ", exit_line, "see decision alpha; don't # or /*")
                self.assertEqual(site_problems(module, cited), [])

    def test_a_merge_stop_needs_a_cite_in_every_raise_form(self):
        for cls in ("Stop", "NetStop", "Dropped", "Held"):
            with self.subTest(cls=cls):
                problems = site_problems("merge", merge_src('raise %s("the lock is not free")' % cls))
                self.assertTrue(uncited_site(problems, "merge"), problems)
                cited = merge_src('raise %s("the lock is not free " + LOCK_CITE)' % cls)
                self.assertEqual(site_problems("merge", cited), [])

    def test_an_fstring_holding_a_cite_constant_passes(self):
        cited = 'CITE = "see decision alpha"\nrefuse(t, "deny", "fstr-id", f"held {CITE}", m)\n'
        self.assertEqual(status_of(cited, "fstr-id"), ["cited"])
        leading = 'CITE = "see decision alpha"\nrefuse(t, "deny", "fstr-lead", f"{CITE} held", m)\n'
        self.assertEqual(status_of(leading, "fstr-lead"), ["cited"])
        uncited = 'NOTE = "no cite"\nrefuse(t, "deny", "fstr-no", f"held {NOTE}", m)\n'
        self.assertEqual(status_of(uncited, "fstr-no"), ["no cite"])

    def test_the_parameter_names_follow_the_defined_signature(self):
        core = "def refuse(tool, decision, reason, rule, matched):\n    pass\n"
        src = 'from guard_core import refuse\nrefuse(t, "deny", "see decision alpha", "sig-id", m)\n'
        self.assertEqual(status_of(src, "sig-id", extra={"guard_core": core}), ["cited"])
        ask = ("def ask_command(reason, rule, matched, command):\n    pass\n"
               'ask_command("see decision alpha", "sig-ask", m, "cmd")\n')
        self.assertEqual(status_of(ask, "sig-ask"), ["cited"])


FAIL = 'def fail(why):\n    raise Stop(why)\n'
MK = 'def mk(what, out):\n    return Stop(what + " " + out)\n'
KEEP = 'def keep(why):\n    raise Stop(why + " stays on branch.")\n'
EXEMPT_REASON = "the run is not in a git checkout, so no merge can start here"


def body_src(body, defs=""):
    """merge/merge.py's stop classes, then `defs`, then `go(b)` with the lines of `body`."""
    return merge_src("pass", defs=defs, body=body)


class RefusalCiteHelperTests(unittest.TestCase):
    """A helper that builds a Stop: its own raise is no site, and each call of it is one, read with the
    call's arguments. A callable parameter bound to a helper, and a Stop that a helper returns, read the same."""

    def test_a_helper_call_with_uncited_text_flags(self):
        self.assertEqual(status_of(body_src('    fail("no cite")\n', FAIL), "merge:go", module="merge"), ["no cite"])

    def test_a_helper_call_with_cited_text_passes(self):
        self.assertEqual(status_of(body_src('    fail("see decision alpha")\n', FAIL), "merge:go", module="merge"), ["cited"])

    def test_a_helper_own_raise_is_no_site(self):
        self.assertEqual(status_of(body_src('    fail("see decision alpha")\n', FAIL), "merge:fail", module="merge"), [])

    def test_a_helper_argument_passed_by_keyword_is_read(self):
        self.assertEqual(status_of(body_src('    fail(why="no cite")\n', FAIL), "merge:go", module="merge"), ["no cite"])

    def test_return_stop_with_uncited_text_flags(self):
        self.assertEqual(status_of(body_src('    return Stop("no cite")\n'), "merge:go", module="merge"), ["no cite"])

    def test_return_stop_with_cited_text_passes(self):
        self.assertEqual(status_of(body_src('    return Stop("see decision alpha")\n'), "merge:go", module="merge"), ["cited"])

    def test_a_stop_built_by_a_helper_and_raised_by_a_caller_is_read(self):
        self.assertEqual(status_of(body_src('    raise mk("no cite", b)\n', MK), "merge:go", module="merge"), ["no cite"])

    def test_a_stop_built_by_a_helper_with_a_cite_passes(self):
        self.assertEqual(status_of(body_src('    raise mk("see decision alpha", b)\n', MK), "merge:go", module="merge"), ["cited"])

    def test_a_callable_parameter_bound_to_a_helper_is_read(self):
        src = body_src('    prove(fail)\n', FAIL + 'def prove(stop):\n    stop("no cite")\n')
        self.assertEqual(status_of(src, "merge:prove", module="merge"), ["no cite"])

    def test_a_callable_parameter_passes_a_cited_argument(self):
        src = body_src('    prove(fail)\n', FAIL + 'def prove(stop):\n    stop("see decision alpha")\n')
        self.assertEqual(status_of(src, "merge:prove", module="merge"), ["cited"])

    def test_a_helper_argument_from_a_run_time_call_is_not_resolved(self):
        self.assertEqual(status_of(body_src('    x = b.run()\n    fail(x)\n', FAIL), "merge:go", module="merge"), ["not resolved"])

    def test_a_caught_stop_re_raised_through_a_helper_is_read_as_cited(self):
        body = '    try:\n        pass\n    except Stop as e:\n        fail(str(e))\n'
        self.assertEqual(status_of(body_src(body, FAIL), "merge:go", module="merge"), ["cited"])

    def test_a_tuple_handler_with_a_non_stop_member_re_raised_through_a_helper_is_not_resolved(self):
        # `except (X, Stop) as e` may bind an X, whose text no origin prints, so its text is not carried.
        for names in ("(OSError, Stop)", "(Stop, OSError)", "(subprocess.TimeoutExpired, Stop)"):
            with self.subTest(names=names):
                body = '    try:\n        pass\n    except %s as e:\n        fail(str(e))\n' % names
                self.assertEqual(status_of(body_src(body, FAIL), "merge:go", module="merge"), ["not resolved"],
                                 "a tuple except with a member that is no Stop name reads as cited")

    def test_a_tuple_handler_of_stop_names_re_raised_through_a_helper_is_read_as_cited(self):
        # Every member is a Stop class, so the bound `e` is always a Stop: its text is printed by its origin.
        for names in ("(Stop, NetStop)", "(NetStop, Dropped)"):
            with self.subTest(names=names):
                body = '    try:\n        pass\n    except %s as e:\n        fail(str(e))\n' % names
                self.assertEqual(status_of(body_src(body, FAIL), "merge:go", module="merge"), ["cited"],
                                 "a tuple except of Stop classes reads as not resolved")

    def test_a_tuple_handler_of_no_stop_re_raised_through_a_helper_is_not_resolved(self):
        body = '    try:\n        pass\n    except (OSError, ValueError) as e:\n        fail(str(e))\n'
        self.assertEqual(status_of(body_src(body, FAIL), "merge:go", module="merge"), ["not resolved"])

    def test_a_tuple_handler_with_a_broad_class_beside_a_stop_re_raised_through_a_helper_is_not_resolved(self):
        # A broad class catches any exception, so the bound `e` is not known to be a Stop.
        for names in ("(Exception, Stop)", "(BaseException, Stop)"):
            with self.subTest(names=names):
                body = '    try:\n        pass\n    except %s as e:\n        fail(str(e))\n' % names
                self.assertEqual(status_of(body_src(body, FAIL), "merge:go", module="merge"), ["not resolved"],
                                 "a tuple handler with a broad class reads as a caught Stop")

    def test_a_caught_generic_exception_re_raised_through_a_helper_is_not_resolved(self):
        body = '    try:\n        pass\n    except Exception as e:\n        fail(str(e))\n'
        self.assertEqual(status_of(body_src(body, FAIL), "merge:go", module="merge"), ["not resolved"])

    def test_a_generic_handler_beside_a_stop_handler_is_not_read_as_cited(self):
        # The Stop handler binds `e` too. The generic handler's `e` is no Stop, so its text is not carried.
        head = '    try:\n        pass\n    except Stop as e:\n        pass\n    except OSError as e:\n'
        for tail in ('        fail(str(e))\n', '        raise Stop(str(e))\n'):
            with self.subTest(tail=tail):
                self.assertEqual(status_of(body_src(head + tail, FAIL), "merge:go", module="merge"), ["not resolved"])

    def test_a_stop_handler_beside_a_generic_handler_still_reads_as_cited(self):
        head = '    try:\n        pass\n    except OSError as e:\n        pass\n    except Stop as e:\n'
        for tail in ('        fail(str(e))\n', '        raise Stop(str(e))\n'):
            with self.subTest(tail=tail):
                self.assertEqual(status_of(body_src(head + tail, FAIL), "merge:go", module="merge"), ["cited"])

    def test_a_generic_handler_inside_a_stop_handler_is_not_read_as_cited(self):
        # The nearest except clause that binds `e` is the generic one, so the Stop above it does not carry.
        body = ('    try:\n        pass\n    except Stop as e:\n        try:\n            pass\n'
                '        except OSError as e:\n            fail(str(e))\n')
        self.assertEqual(status_of(body_src(body, FAIL), "merge:go", module="merge"), ["not resolved"])

    def test_a_nested_def_that_only_returns_is_no_site(self):
        body = '    def keep(why):\n        return False\n    return keep("see decision alpha")\n'
        src = body_src(body)
        self.assertEqual(status_of(src, "merge:go", module="merge"), [])
        self.assertEqual(status_of(src, "merge:keep", module="merge"), [])

    def test_a_helper_passed_on_without_a_call_is_a_direct_site(self):
        src = body_src('    store(fail)\n', FAIL + 'def store(cb):\n    return cb\n')
        self.assertEqual(status_of(src, "merge:fail", module="merge"), ["not resolved"])

    def test_a_method_raise_with_a_parameter_is_a_direct_site(self):
        defs = 'class Host:\n    def pages(self, rel):\n        raise Stop(f"reading {rel} failed")\n'
        self.assertEqual(status_of(body_src('    Host().pages("x")\n', defs), "merge:Host.pages", module="merge"), ["no cite"])

    def test_a_helper_with_static_text_reads_its_argument_uncited(self):
        self.assertEqual(status_of(body_src('    keep("no cite")\n', KEEP), "merge:go", module="merge"), ["no cite"])

    def test_a_helper_with_static_text_reads_its_argument_cited(self):
        self.assertEqual(status_of(body_src('    keep("see decision alpha")\n', KEEP), "merge:go", module="merge"), ["cited"])

    def test_comment_openers_and_a_lone_quote_in_a_helper_argument_are_text(self):
        body = '    fail("a # and /* and // in text, Don\'t refuse")\n'
        self.assertEqual(status_of(body_src(body, FAIL), "merge:go", module="merge"), ["no cite"])

    def test_a_helper_argument_over_several_lines_that_cites_passes(self):
        body = '    fail("""two\nlines, see decision alpha""")\n'
        self.assertEqual(status_of(body_src(body, FAIL), "merge:go", module="merge"), ["cited"])

    def test_a_same_named_helper_in_another_function_is_no_site(self):
        defs = 'def other():\n    def fail(why):\n        raise Stop(why)\n'
        self.assertEqual(status_of(body_src('    fail("no cite")\n', defs), "merge:go", module="merge"), [])

    def test_a_helper_call_inside_a_lambda_is_read(self):
        defs = FAIL + 'def retry(fn):\n    return fn()\n'
        self.assertEqual(status_of(body_src('    retry(lambda: fail("no cite"))\n', defs), "merge:go", module="merge"), ["no cite"])

    def test_an_aliased_refuse_import_is_a_site(self):
        src = 'from guard_core import refuse as r\ndef go(t, m):\n    r(t, "deny", "alias-id", "no cite", m)\n'
        extra = {"guard_core": 'def refuse(tool, decision, rule, reason, matched):\n    pass\n'}
        self.assertEqual(status_of(src, "alias-id", extra=extra), ["no cite"])

    def test_an_attribute_read_of_a_helper_name_does_not_make_it_a_direct_site(self):
        # `opts.keep` reads an attribute of some object, not the helper, so the helper stays a helper.
        src = body_src('    keep("see decision alpha")\n', KEEP)
        extra = {"guard": "def read(opts):\n    return opts.keep\n"}
        self.assertEqual(status_of(src, "merge:keep", extra=extra, module="merge"), [])
        self.assertEqual(status_of(src, "merge:go", extra=extra, module="merge"), ["cited"])

    def test_a_name_another_module_imports_from_the_helper_module_is_no_helper(self):
        src = body_src('    keep("see decision alpha")\n', KEEP)
        extra = {"guard": "from merge import keep\n"}
        self.assertEqual(status_of(src, "merge:keep", extra=extra, module="merge"), ["no cite"])

    def test_a_name_read_through_the_helper_module_alias_is_no_helper(self):
        src = body_src('    keep("see decision alpha")\n', KEEP)
        extra = {"guard": "import merge as m\ndef read():\n    return m.keep\n"}
        self.assertEqual(status_of(src, "merge:keep", extra=extra, module="merge"), ["no cite"])
    def test_a_name_read_through_a_dotted_import_of_the_helper_module_is_no_helper(self):
        src = body_src('    keep("see decision alpha")\n', KEEP)
        extra = {"guard": "import merge.merge\ndef read():\n    return merge.merge.keep\n"}
        self.assertEqual(status_of(src, "merge:keep", extra=extra, module="merge"), ["no cite"])


class RefusalJoinTests(unittest.TestCase):
    """A refusal built by `"<sep>".join([...])` with literal separator and list: its static lines are its text,
    as a `+` chain's are. The reader reads it as text, so a cite or a missing cite inside it is judged."""

    def test_a_join_of_static_lines_with_no_cite_is_read_as_no_cite(self):
        src = body_src('    raise Stop("\\n".join(["cannot make the thing:", "detail"]))\n')
        self.assertEqual(status_of(src, "merge:go", module="merge"), ["no cite"],
                         "a join of static lines is read as not resolved, not as its text")

    def test_a_join_with_a_cited_line_passes(self):
        src = body_src('    raise Stop("\\n".join(["cannot make the thing:", "see decision alpha"]))\n')
        self.assertEqual(status_of(src, "merge:go", module="merge"), ["cited"],
                         "a join with a cited line is read as not resolved, not as cited")

    def test_a_join_held_in_a_name_is_read_through_the_name(self):
        body = '    body = "\\n".join(["cannot make the thing:", "detail"])\n    raise Stop(body)\n'
        self.assertEqual(status_of(body_src(body), "merge:go", module="merge"), ["no cite"],
                         "a join held in a local name is read as not resolved, not as its text")

    def test_a_run_time_line_in_a_join_adds_no_text_and_the_static_lines_still_count(self):
        src = body_src('    raise Stop("\\n".join([f"cannot do {b}:", *b.lines]))\n')
        self.assertEqual(status_of(src, "merge:go", module="merge"), ["no cite"],
                         "a join with a run-time line is read as not resolved, not as its static text")

    def test_a_join_with_no_static_line_stays_not_resolved(self):
        # The control: these read as not resolved before the reader read joins, and must after it too.
        self.assertEqual(status_of(body_src('    raise Stop("\\n".join(b.lines))\n'), "merge:go", module="merge"),
                         ["not resolved"])
        self.assertEqual(status_of(body_src('    raise Stop("\\n".join([]))\n'), "merge:go", module="merge"),
                         ["not resolved"])


KIND_FAIL ='def fail(why, kind=Stop):\n    raise kind(why)\n'  # the kind parameter of merge/merge.py's fail()
LIFT = 'class Liftable(Stop):\n    """A refusal the owner may lift."""\n'


class RefusalKindParameterTests(unittest.TestCase):
    """A raise through a parameter that defaults to a Stop class, as `fail(why, kind=Stop)` in merge/merge.py:
    each call of that helper is a site. A Stop subclass is read from its base, a plain name or an attribute."""

    def test_a_kind_parameter_raise_reads_an_uncited_call(self):
        self.assertEqual(status_of(body_src('    fail("no cite")\n', KIND_FAIL), "merge:go", module="merge"), ["no cite"])

    def test_a_kind_parameter_raise_passes_a_cited_call(self):
        self.assertEqual(status_of(body_src('    fail("see decision alpha")\n', KIND_FAIL), "merge:go", module="merge"), ["cited"])

    def test_a_kind_keyword_on_the_call_leaves_the_message_read(self):
        src = body_src('    fail("no cite", kind=Liftable)\n', LIFT + KIND_FAIL)
        self.assertEqual(status_of(src, "merge:go", module="merge"), ["no cite"])

    def test_a_liftable_default_kind_is_read_through_its_derived_class(self):
        src = body_src('    lift("no cite")\n', LIFT + 'def lift(why, kind=Liftable):\n    raise kind(why)\n')
        self.assertEqual(status_of(src, "merge:go", module="merge"), ["no cite"])

    def test_a_kind_parameter_that_is_not_a_stop_class_is_no_site(self):
        # The boundary: a non-Stop default, or no default, makes the raise no Stop, so its helper is no site.
        other = 'def fail(why, kind=ValueError):\n    raise kind(why)\n'
        self.assertEqual(status_of(body_src('    fail("no cite")\n', other), "merge:go", module="merge"), [])
        bare = 'def fail(why, kind):\n    raise kind(why)\n'
        self.assertEqual(status_of(body_src('    fail("no cite", Liftable)\n', LIFT + bare), "merge:go", module="merge"), [])

    def test_a_stop_subclass_with_an_attribute_base_is_a_stop(self):
        src = body_src('    raise Lift("no cite")\n', 'class Lift(stops.Stop):\n    """A refusal."""\n')
        self.assertEqual(status_of(src, "merge:go", module="merge"), ["no cite"])


class RefusePrintTests(unittest.TestCase):
    """A refuse print is a refusal site: a decision "block" that reaches the output, whatever its shape: a dict literal,
    a keyword call (`out.update` or `dict`), an `out["decision"] = ...` assignment, or a reason built at run time. Any
    module in scope counts, not only a Stop hook. A print with no reason, or a reason the scan cannot read, is `not
    resolved`. A decision the scan cannot read, a dict nothing prints, and a decision that is not "block" are no site."""

    def test_a_refuse_print_dict_with_a_cite_passes(self):
        src = 'import json\ndef stop():\n    print(json.dumps({"decision": "block", "reason": "held, see decision alpha"}))\n'
        self.assertEqual(status_of(src, "guard:stop"), ["cited"])

    def test_a_refuse_print_dict_with_no_cite_is_no_cite(self):
        src = 'import json\ndef stop():\n    print(json.dumps({"decision": "block", "reason": "held, see decision beta"}))\n'
        self.assertEqual(status_of(src, "guard:stop"), ["no cite"])

    def test_a_refuse_print_keyword_update_with_a_cite_passes(self):
        src = ('import json\ndef stop(out):\n    out.update(decision="block", reason="held, see decision alpha")\n'
               '    print(json.dumps(out))\n')
        self.assertEqual(status_of(src, "guard:stop"), ["cited"])

    def test_a_refuse_print_keyword_update_with_no_cite_is_no_cite(self):
        src = ('import json\ndef stop(out):\n    out.update(decision="block", reason="held, see decision beta")\n'
               '    print(json.dumps(out))\n')
        self.assertEqual(status_of(src, "guard:stop"), ["no cite"])

    def test_a_refuse_print_keyword_dict_call_is_a_site(self):
        src = 'import json\ndef stop():\n    print(json.dumps(dict(decision="block", reason="held, see decision beta")))\n'
        self.assertEqual(status_of(src, "guard:stop"), ["no cite"])

    def test_a_refuse_print_keyword_reason_passed_in_as_a_parameter_is_not_resolved(self):
        src = 'import json\ndef stop(out, why):\n    out.update(decision="block", reason=why)\n    print(json.dumps(out))\n'
        self.assertEqual(status_of(src, "guard:stop"), ["not resolved"])

    def test_a_refuse_print_reason_from_a_def_that_cites_nothing_is_no_cite(self):
        src = ('import json\n'
               'def run(hook):\n'
               '    return "Ruling home: this turn\'s memory names no tracked home."\n'
               'def main(hook):\n'
               '    reason = run(hook)\n'
               '    if reason:\n'
               '        print(json.dumps({"decision": "block", "reason": reason}))\n')
        self.assertEqual(status_of(src, "guard:main"), ["no cite"])
        cited = src.replace("tracked home.", "tracked home, see decision alpha.")
        self.assertEqual(status_of(cited, "guard:main"), ["cited"])

    def test_a_refuse_print_joined_at_run_time_judges_its_static_tail(self):
        src = ('import json\n'
               'CORRECTION_TAIL = " Post only the corrected lines."\n'
               'def main(reasons):\n'
               '    print(json.dumps({"decision": "block", "reason": " ".join(reasons) + CORRECTION_TAIL}))\n')
        self.assertEqual(status_of(src, "guard:main"), ["no cite"])
        cited = src.replace("corrected lines.", "corrected lines, see decision alpha.")
        self.assertEqual(status_of(cited, "guard:main"), ["cited"])

    def test_a_refuse_print_built_from_a_table_and_a_def_is_judged_on_its_text(self):
        defs = ('def diff_rule(role):\n    return {"a": "author-diff"}.get(role, "builder-diff")\n'
                'def builder_text():\n    return "A builder changes no test. Report it."\n')
        src = 'import json\n' + defs + ('def stop(role):\n'
              '    print(json.dumps({"decision": "block", "reason": diff_rule(role) + ": " + builder_text()}))\n')
        self.assertEqual(status_of(src, "guard:stop"), ["no cite"])
        cited = src.replace("Report it.", "Report it. (decision alpha)")
        self.assertEqual(status_of(cited, "guard:stop"), ["cited"])

    def test_a_refuse_print_reason_that_is_a_name_of_the_enclosing_def_is_not_resolved(self):
        src = ('import json\n'
               'def main(refusal):\n'
               '    def stop_for_refusal():\n'
               '        if refusal:\n'
               '            print(json.dumps({"decision": "block", "reason": refusal}))\n'
               '    stop_for_refusal()\n')
        self.assertEqual(status_of(src, "guard:stop_for_refusal"), ["not resolved"])

    def test_a_refuse_print_with_no_reason_key_is_not_resolved(self):
        src = 'import json\ndef stop():\n    print(json.dumps({"decision": "block"}))\n'
        self.assertEqual(status_of(src, "guard:stop"), ["not resolved"])

    def test_a_refuse_print_reason_passed_in_as_a_parameter_is_not_resolved(self):
        src = 'import json\ndef go(why):\n    print(json.dumps({"decision": "block", "reason": why}))\n'
        self.assertEqual(status_of(src, "guard:go"), ["not resolved"])

    def test_a_refuse_print_reason_from_a_format_string_is_read(self):
        src = ('import json\ndef stop(handoff):\n'
               '    print(json.dumps({"decision": "block", "reason": "Rewrite your handoff at %s now, see decision alpha." % handoff}))\n')
        self.assertEqual(status_of(src, "guard:stop"), ["cited"])

    def test_comment_openers_inside_a_refuse_print_reason_are_text(self):
        cited = ('import json\ndef stop():\n'
                 '    print(json.dumps({"decision": "block", "reason": "use the # sign, a /* and // here, see decision alpha"}))\n')
        self.assertEqual(status_of(cited, "guard:stop"), ["cited"])
        uncited = ('import json\ndef stop():\n'
                   '    print(json.dumps({"decision": "block", "reason": "a # and /* and // in text, Don\'t stop"}))\n')
        self.assertEqual(status_of(uncited, "guard:stop"), ["no cite"])

    def test_a_trailing_comment_with_a_cite_is_not_the_reason(self):
        src = ('import json\ndef stop():\n'
               '    print(json.dumps({"decision": "block", "reason": "no cite here"}))  # see decision alpha\n')
        self.assertEqual(status_of(src, "guard:stop"), ["no cite"])

    def test_a_refuse_print_reason_over_several_lines_reads_every_line(self):
        cited = ('import json\ndef stop():\n'
                 '    print(json.dumps({"decision": "block", "reason": (\n'
                 '        "Context is about 334k tokens, "\n'
                 '        "messages about 249k. "\n'
                 '        "Follow step 4 of the prompt, see decision alpha."\n'
                 '    )}))\n')
        self.assertEqual(status_of(cited, "guard:stop"), ["cited"])
        self.assertEqual(status_of(cited.replace("see decision alpha", "see decision beta"), "guard:stop"), ["no cite"])
        triple = ('import json\ndef stop():\n'
                  '    print(json.dumps({"decision": "block", "reason": """first line\n'
                  'second line, see decision alpha"""}))\n')
        self.assertEqual(status_of(triple, "guard:stop"), ["cited"])

    def test_a_refuse_print_in_a_judge_module_is_a_site(self):
        src = 'import json\ndef stop():\n    print(json.dumps({"decision": "block", "reason": "no cite"}))\n'
        statuses, _ = refusal_status({"judge": src}, HOMES, {"judge"}, guards=set())
        self.assertEqual([s for _, s, _ in statuses.get("judge:stop", [])], ["no cite"])

    def test_two_refuse_prints_in_one_function_each_read_their_own_site(self):
        src = ('import json\ndef stop(out):\n'
               '    print(json.dumps({"decision": "block", "reason": "held, see decision alpha"}))\n'
               '    out.update(decision="block", reason="no cite here")\n'
               '    print(json.dumps(out))\n')
        self.assertEqual(status_of(src, "guard:stop"), ["cited", "no cite"])

    def test_a_decision_that_is_not_block_is_no_site(self):
        # A control: a decision other than "block" is no site, so it can never turn a refusal red.
        src = ('import json\ndef stop():\n'
               '    print(json.dumps({"decision": "approve", "reason": "no cite"}))\n'
               '    print(json.dumps({"decision": {"behavior": "allow"}, "reason": "no cite"}))\n')
        statuses, _ = refusal_status({"guard": src}, HOMES, SCOPE)
        self.assertEqual(statuses, {})

    def test_a_module_with_no_refuse_print_is_no_site(self):
        # A control: an empty module has no site and no unattributed call.
        statuses, unattributed = refusal_status({"guard": ""}, HOMES, SCOPE)
        self.assertEqual((statuses, unattributed), ({}, []))

    def test_a_refuse_print_subscript_decision_is_a_site(self):
        src = ('import json\ndef stop():\n    out = {}\n    out["decision"] = "block"\n'
               '    out["reason"] = "held, see decision beta"\n    print(json.dumps(out))\n')
        self.assertEqual(status_of(src, "guard:stop"), ["no cite"])
        self.assertEqual(status_of(src.replace("decision beta", "decision alpha"), "guard:stop"), ["cited"])

    def test_a_refuse_print_module_constant_decision_is_a_site(self):
        src = ('import json\nBLOCK = "block"\ndef stop():\n'
               '    print(json.dumps({"decision": BLOCK, "reason": "held, see decision beta"}))\n')
        self.assertEqual(status_of(src, "guard:stop"), ["no cite"])

    def test_a_refuse_print_ternary_decision_is_a_site(self):
        src = ('import json\ndef stop(hold):\n'
               '    print(json.dumps({"decision": "block" if hold else "approve", "reason": "held, see decision beta"}))\n')
        self.assertEqual(status_of(src, "guard:stop"), ["no cite"])

    def test_a_decision_of_approve_by_name_or_by_ternary_is_no_site(self):
        src = ('import json\nAPPROVE = "approve"\ndef stop(hold):\n'
               '    print(json.dumps({"decision": APPROVE, "reason": "no cite"}))\n'
               '    print(json.dumps({"decision": "approve" if hold else "approve", "reason": "no cite"}))\n')
        statuses, _ = refusal_status({"guard": src}, HOMES, SCOPE)
        self.assertEqual(statuses, {})

    def test_a_refuse_print_appended_to_a_log_is_no_site(self):
        src = 'LOG = []\ndef stop():\n    LOG.append({"decision": "block", "reason": "no cite"})\n'
        statuses, _ = refusal_status({"guard": src}, HOMES, SCOPE)
        self.assertEqual(statuses, {})

    def test_a_refuse_print_dict_printed_through_a_name_is_a_site(self):
        src = ('import json\ndef stop():\n'
               '    payload = {"decision": "block", "reason": "held, see decision beta"}\n'
               '    print(json.dumps(payload))\n')
        self.assertEqual(status_of(src, "guard:stop"), ["no cite"])

    def test_a_refuse_print_keyword_update_printed_through_a_name_is_a_site(self):
        src = ('import json\ndef stop(out):\n    out.update(decision="block", reason="held, see decision beta")\n'
               '    print(json.dumps(out))\n')
        self.assertEqual(status_of(src, "guard:stop"), ["no cite"])

    def test_a_helper_reads_the_reason_at_each_call_and_its_own_print_is_no_site(self):
        src = ('import json\ndef emit(reason):\n'
               '    print(json.dumps({"decision": "block", "reason": reason}))\n'
               'def stop():\n'
               '    emit("held, see decision alpha")\n'
               '    emit("held, no cite")\n')
        self.assertEqual(status_of(src, "guard:stop"), ["cited", "no cite"])
        self.assertEqual(status_of(src, "guard:emit"), [], "the helper's own print reads its call sites instead")

    def test_a_joined_reason_whose_tail_alone_cites_is_no_cite(self):
        src = ('import json\nCORRECTION_TAIL = " Post only the corrected lines, see decision alpha."\n'
               'def main(reasons, short):\n'
               '    print(json.dumps({"decision": "block", "reason": " ".join(reasons) + (CORRECTION_TAIL if not short else "")}))\n')
        self.assertEqual(status_of(src, "guard:main"), ["no cite"])

    def test_a_joined_reason_with_a_cite_before_its_falsy_tail_is_cited(self):
        src = ('import json\nCORRECTION_TAIL = " Post only the corrected lines."\n'
               'def main(reasons, short):\n'
               '    print(json.dumps({"decision": "block", "reason": " ".join(reasons) + " (decision alpha)" + (CORRECTION_TAIL if not short else "")}))\n')
        self.assertEqual(status_of(src, "guard:main"), ["cited"])

    def test_a_whole_reason_that_is_a_cite_or_falsy_keeps_the_falsy_branch_out(self):
        src = ('import json\nTAIL = "Stop here, see decision alpha."\n'
               'def main(short):\n'
               '    print(json.dumps({"decision": "block", "reason": (TAIL if not short else "")}))\n')
        self.assertEqual(status_of(src, "guard:main"), ["cited"])


RULE_HOMES = ({"alpha"}, {"anchor-one", "reports-order-of-labels"})  # the rule anchor that report_guard's block reasons end with
UNCITED_BLOCK = '{"decision": "block", "reason": "held, see decision beta, don\'t # or /* or //"}'
CITED_BLOCK = '{"decision": "block", "reason": "held, see decision alpha, don\'t # or /* or //"}'
UNCITED_TERNARY = '{"decision": "block", "reason": "held, see decision beta"} if hold else None'
CITED_TERNARY = '{"decision": "block", "reason": "held, see decision alpha"} if hold else None'
CITED_LINES = '{"decision": "block", "reason": (\n        "held, "\n        "see decision alpha"\n    )}'
# report_guard.main()'s finish(payload) as a closure, its body as there; `route` is a parameter of main.
FINISH_CLOSURE = ('    def finish(payload):\n'
                  '        if route:\n'
                  '            payload = dict(payload or {})\n'
                  '            payload["systemMessage"] = " ".join(filter(None, [payload.get("systemMessage"), *route]))\n'
                  '        if payload:\n'
                  '            print(json.dumps(payload))\n')
EMIT_MODULE = 'def emit(p):\n    if p:\n        print(json.dumps(p))\n'  # the same print as a module-level helper


def call_of(name, arg):
    """One line of main's body: a call of `name` with `arg` as its argument."""
    return "    %s(%s)\n" % (name, arg)


def closure_src(call):
    """report_guard.main() with its closure `finish`, and the lines `call` of main's body."""
    return "import json\ndef main(route, hold, pick):\n" + FINISH_CLOSURE + call


def module_src(call):
    """The print as a module-level helper `emit`, and the lines `call` of main's body."""
    return "import json\n" + EMIT_MODULE + "def main(route, hold, pick):\n" + call


def call_rows(src, homes=HOMES):
    """-> {refusal id: [status]} for one guard module's source."""
    statuses, _ = refusal_status({"guard": src}, homes, SCOPE)
    return {rid: [s for _, s, _ in rows] for rid, rows in statuses.items()}


REACH_BUDGET = 400  # calls of _reaches_output that a scan of the six-rebind fixtures may make, with room to spare


def reach_calls(src, budget=REACH_BUDGET):
    """-> (calls, rows): the calls a scan of `src` makes to _reaches_output, and its rows. Past `budget` a call
    returns at once with no output, so a read that grows past it fails the count and stops there."""
    real = _reaches_output
    calls = [0]

    def counted(node, mod, scope, depth=0, returns=True):
        calls[0] += 1
        return False if calls[0] > budget else real(node, mod, scope, depth, returns)

    with mock.patch.object(sys.modules[__name__], "_reaches_output", counted):
        rows = call_rows(src)
    return calls[0], rows


SIX_REBINDS = "".join("    out = dict(out, a%d=%d)\n" % (i, i) for i in range(1, 7))


class RefuseHelperArgumentTests(unittest.TestCase):
    """A block dict passed to a helper that prints its parameter is a refuse site, read at each call as a refuse
    print is: its id is the caller's `module:function`, and its reason is read at the call. The dict may be a
    literal, a `dict(key=value)` call, or either branch of an `A if c else B`. A helper that passes its parameter to
    a printing helper prints it too. A helper that only stores its parameter, a parameter rebound to another
    value, a value that is only returned, and a dict that is not a block, are no site.

    Known gaps, not built: a block dict bound to a name first, and then passed to a printing helper, is not read.
    A dict literal that holds the parameter, such as `{"hookSpecificOutput": p}`, is not read. A rebinding in both
    branches of an if/else hides nothing, so a block dict that both branches replace reads as printed (a false
    alarm). No case here covers these."""

    def assertReadAtCall(self, src, status, homes=HOMES):
        """The scope first: main is the only refusal id. Then the subject: the call's reason reads as `status`."""
        rows = call_rows(src, homes)
        self.assertEqual(sorted(rows), ["guard:main"], "the call is no refuse site of main")
        self.assertEqual(rows.get("guard:main"), [status], "the call's reason does not read as %s" % status)

    def test_a_closure_that_prints_a_block_dict_argument_reads_an_uncited_call(self):
        for form, arg in (("plain", UNCITED_BLOCK), ("ternary", UNCITED_TERNARY)):
            with self.subTest(form=form):
                self.assertReadAtCall(closure_src(call_of("finish", arg)), "no cite")

    def test_a_closure_that_prints_a_block_dict_argument_passes_a_cited_call(self):
        for form, arg in (("plain", CITED_BLOCK), ("ternary", CITED_TERNARY), ("two lines", CITED_LINES)):
            with self.subTest(form=form):
                self.assertReadAtCall(closure_src(call_of("finish", arg)), "cited")

    def test_a_module_helper_that_prints_a_block_dict_argument_reads_an_uncited_call(self):
        for form, arg in (("plain", UNCITED_BLOCK), ("ternary", UNCITED_TERNARY)):
            with self.subTest(form=form):
                self.assertReadAtCall(module_src(call_of("emit", arg)), "no cite")

    def test_a_module_helper_that_prints_a_block_dict_argument_passes_a_cited_call(self):
        for form, arg in (("plain", CITED_BLOCK), ("ternary", CITED_TERNARY), ("two lines", CITED_LINES)):
            with self.subTest(form=form):
                self.assertReadAtCall(module_src(call_of("emit", arg)), "cited")

    def test_a_helper_that_only_stores_a_block_dict_argument_is_no_site(self):
        # A control: a stored argument is never printed, so no refusal is read.
        src = ("LOG = []\ndef record(p):\n    if p:\n        LOG.append(p)\n"
               "def main(route, hold, pick):\n" + call_of("record", UNCITED_BLOCK))
        self.assertEqual(call_rows(src), {}, "a helper that stores its argument is read as a refusal")

    def test_a_helper_that_prints_a_dict_that_is_no_block_is_no_site(self):
        # A control: a dict that is no block is no refusal, however the helper prints it.
        for form, arg in (("systemMessage", '{"systemMessage": "held, no cite"}'),
                          ("approve", '{"decision": "approve", "reason": "held, no cite"}')):
            with self.subTest(form=form):
                self.assertEqual(call_rows(closure_src(call_of("finish", arg))), {},
                                 "a dict that is no block is read as a refusal")

    def test_a_block_reason_joined_with_a_rule_tail_reads_cited(self):
        call = ('    reason = " ".join(pick) + " (rule reports-order-of-labels)"\n'
                '    finish({"decision": "block", "reason": reason})\n')
        src = closure_src(call)
        self.assertReadAtCall(src, "cited", RULE_HOMES)
        # The twin: the same reason, with homes that do not name the tail's anchor, reads no cite.
        self.assertEqual(call_rows(src).get("guard:main"), ["no cite"], "the tail's rule anchor does not decide the cite")


    def test_a_dict_call_passed_to_a_printing_helper_reads_its_reason(self):
        for arg, status in (('dict(decision="block", reason="held, no cite")', "no cite"),
                            ('dict(decision="block", reason="held, see decision alpha")', "cited")):
            with self.subTest(arg=arg):
                self.assertReadAtCall(closure_src(call_of("finish", arg)), status)

    def test_a_helper_that_passes_its_parameter_to_a_printing_helper_reads_the_call(self):
        relay = ("import json\ndef emit(p):\n    if p:\n        print(json.dumps(p))\n"
                 "def finish(p):\n    emit(p)\ndef main(route, hold, pick):\n")
        for arg, status in ((UNCITED_BLOCK, "no cite"), (CITED_BLOCK, "cited")):
            with self.subTest(arg=status):
                self.assertReadAtCall(relay + call_of("finish", arg), status)

    def test_a_block_dict_passed_to_a_parameter_that_is_never_printed_is_no_site(self):
        # A control: the dict is stored one call down, and the other parameter is the one printed.
        src = ("import json\nLOG = []\ndef keep(p):\n    LOG.append(p)\n"
               "def finish(p, q):\n    keep(p)\n    if q:\n        print(json.dumps(q))\n"
               "def main(route, hold, pick):\n" + call_of("finish", UNCITED_BLOCK + ", None"))
        self.assertEqual(call_rows(src), {}, "a block dict in a parameter that is never printed is read as a refusal")

    def test_a_block_dict_returned_by_a_helper_and_never_printed_is_no_site(self):
        # A control: the returned dict is appended to a list that nothing prints.
        src = ("import json\nLOG = []\ndef tag(p):\n    return p\n"
               "def main(route, hold, pick):\n    LOG.append(tag(" + UNCITED_BLOCK + "))\n")
        self.assertEqual(call_rows(src), {}, "a returned block dict that is never printed is read as a refusal")

    def test_a_parameter_rebound_to_another_value_before_its_print_is_no_site(self):
        rebound = ("import json\ndef finish(p):\n    p = {\"systemMessage\": \"held, no cite\"}\n"
                   "    if p:\n        print(json.dumps(p))\ndef main(route, hold, pick):\n")
        self.assertEqual(call_rows(rebound + call_of("finish", UNCITED_BLOCK)), {},
                         "the caller's block dict is read as printed after the parameter was rebound")
        # The real finish() rebinds its parameter from itself, and what it prints still holds the caller's dict.
        derived = ("import json\ndef finish(p):\n    p = dict(p or {})\n"
                   "    if p:\n        print(json.dumps(p))\ndef main(route, hold, pick):\n")
        self.assertReadAtCall(derived + call_of("finish", UNCITED_BLOCK), "no cite")


    def test_a_parameter_passed_around_a_cycle_of_helpers_reads_the_call(self):
        # Mutual recursion: the printer table must reach its fixed point and stop, not loop.
        cycle = ("import json\ndef b(p):\n    a(p)\n    print(json.dumps(p))\n"
                 "def a(p):\n    b(p)\ndef main(route, hold, pick):\n")
        self.assertReadAtCall(cycle + call_of("a", UNCITED_BLOCK), "no cite")


    def test_a_dict_rebound_six_times_by_a_helper_that_returns_it_is_read_in_bounded_work(self):
        src = ("import json\ndef helper(p):\n    out = dict(p)\n" + SIX_REBINDS + "    return out\n"
               "def main(route, hold, pick):\n" + call_of("helper", UNCITED_BLOCK))
        calls, rows = reach_calls(src)
        self.assertLessEqual(calls, REACH_BUDGET, "the printer read walks more paths than six rebinds need")
        self.assertEqual(rows, {}, "a returned dict that nothing prints is read as a refusal")

    def test_a_block_dict_rebound_six_times_and_only_appended_is_read_in_bounded_work(self):
        src = ("import json\nLOG = []\ndef main(route, hold, pick):\n"
               '    out = dict(decision="block", reason="held, no cite")\n' + SIX_REBINDS + "    LOG.append(out)\n")
        calls, rows = reach_calls(src)
        self.assertLessEqual(calls, REACH_BUDGET, "the refuse read of a dict walks more paths than six rebinds need")
        self.assertEqual(rows, {}, "a block dict that nothing prints is read as a refusal")

    def test_a_rebinding_inside_one_branch_hides_nothing_from_the_print(self):
        for form, branch in (("if", "    if not p:\n        p = {\"systemMessage\": \"held, no cite\"}\n"),
                             ("if-else", "    if not p:\n        p = {\"systemMessage\": \"held, no cite\"}\n"
                                         "    else:\n        pass\n")):
            with self.subTest(form=form):
                src = ("import json\ndef finish(p):\n" + branch + "    print(json.dumps(p))\n"
                       "def main(route, hold, pick):\n" + call_of("finish", UNCITED_BLOCK))
                self.assertReadAtCall(src, "no cite")

    def test_a_parameter_printed_through_or_or_a_conditional_expression_reads_the_call(self):
        for form in ("json.dumps(p or {})", "json.dumps(p if p else {})"):
            with self.subTest(form=form):
                src = ("import json\ndef finish(p):\n    print(%s)\n" % form
                       + "def main(route, hold, pick):\n" + call_of("finish", UNCITED_BLOCK))
                self.assertReadAtCall(src, "no cite")


class RefuseReasonDepthTests(unittest.TestCase):
    """A reason is read through the names that bind it, one hop each, up to MAX_DEPTH. A cite past the old cap of
    12 hops reads cited."""

    def test_a_cite_twenty_name_hops_from_the_reason_reads_cited(self):
        chain = '    r0 = "held, see decision alpha"\n' + "".join("    r%d = r%d\n" % (i, i - 1) for i in range(1, 21))
        src = closure_src(chain + call_of("finish", '{"decision": "block", "reason": r20}'))
        rows = call_rows(src)
        self.assertEqual(sorted(rows), ["guard:main"], "the call is no refuse site of main")
        self.assertEqual(rows.get("guard:main"), ["cited"],
                         "a cite 20 name hops from the reason does not read as cited (the depth cap)")


class SettingsScriptFormTests(unittest.TestCase):
    """The script a settings.json command runs, read from each form a command may name it by."""

    def wired(self, command):
        data = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": command}]}]}}
        with mock.patch("builtins.open", mock.mock_open(read_data=json.dumps(data))):
            return settings_scripts("/repo")

    def test_the_config_dir_default_form_names_its_script(self):
        self.assertEqual(self.wired('python3 "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/hooks/alpha_guard.py"'),
                         ["hooks/alpha_guard.py"])

    def test_a_tilde_form_names_its_script(self):
        self.assertEqual(self.wired("python3 ~/.claude/hooks/beta_guard.py"), ["hooks/beta_guard.py"])

    def test_a_home_variable_form_names_its_script(self):
        self.assertEqual(self.wired('python3 "$HOME/.claude/hooks/gamma_guard.py"'), ["hooks/gamma_guard.py"])

    def test_a_repo_relative_form_names_its_script(self):
        self.assertEqual(self.wired("python3 lint/delta_check.py"), ["lint/delta_check.py"])


class RefusalCiteRatchetTests(unittest.TestCase):
    """The exempt list: an uncited id must be exempt with a home, and an entry must still be needed."""

    SRC = 'refuse(t, "deny", "bare-id", "no cite here", m)\n'

    def problems(self, exempt, src=None, scope=SCOPE):
        return refusal_problems({"guard": self.SRC if src is None else src}, HOMES, exempt, scope)

    def test_an_uncited_id_not_in_the_exempt_list_fails_and_names_its_site(self):
        problems = self.problems({})
        self.assertEqual(problems, ["bare-id: guard.py:1 no cite"])

    def test_an_uncited_id_with_a_home_passes(self):
        self.assertEqual(self.problems({"bare-id": "step-one"}), [])

    def test_an_exempt_id_that_no_refusal_prints_is_stale(self):
        problems = self.problems({"bare-id": "step-one", "gone-id": "step-one"})
        self.assertEqual(problems, ["gone-id: remove from exempt; no refusal prints it"])

    def test_an_exempt_id_that_now_cites_is_stale(self):
        src = 'refuse(t, "deny", "bare-id", "see decision alpha", m)\n'
        self.assertEqual(self.problems({"bare-id": "step-one"}, src),
                         ["bare-id: remove from exempt; every site now cites"])

    def test_an_exempt_home_must_be_a_slug(self):
        self.assertEqual(self.problems({"bare-id": "Not A Slug"}),
                         ["bare-id: exempt home `Not A Slug` is not a step slug or debt id"])

    def test_an_id_with_one_cited_and_one_uncited_site_fails_unless_exempt(self):
        src = ('refuse(t, "deny", "bare-id", "see decision alpha", m)\n'
               'refuse(t, "deny", "bare-id", "no cite", m)\n')
        self.assertEqual(self.problems({}, src), ["bare-id: guard.py:2 no cite"])

    def test_an_unresolved_reason_fails_with_its_own_label(self):
        src = 'def go(reason):\n    refuse(t, "deny", "param-id", reason, m)\n'
        self.assertEqual(self.problems({}, src), ["param-id: guard.py:2 not resolved"])

    def test_a_new_uncited_stop_in_an_exempt_function_goes_red(self):
        src = body_src('    raise Stop("not in a git checkout")\n    raise Stop("a brand new uncited refusal")\n')
        line = next(i for i, text in enumerate(src.splitlines(), 1) if "brand new" in text)
        exempt = {"merge:go: not in a git checkout": ("refusal-matches-rule", EXEMPT_REASON)}
        self.assertEqual(module_problems(src, exempt), ["merge:go: merge.py:%d no cite" % line])

    def test_an_exempt_prefix_that_names_the_site_passes(self):
        src = body_src('    raise Stop("not in a git checkout")\n')
        exempt = {"merge:go: not in a git checkout": ("refusal-matches-rule", EXEMPT_REASON)}
        self.assertEqual(module_problems(src, exempt), [])

    def test_an_exempt_prefix_that_matches_two_sites_is_a_problem(self):
        src = body_src('    raise Stop("not in a git checkout")\n    raise Stop("not in a git checkout")\n')
        exempt = {"merge:go: not in a git checkout": ("refusal-matches-rule", EXEMPT_REASON)}
        self.assertTrue(any("matches 2 sites" in p for p in module_problems(src, exempt)))

    def test_an_exempt_function_key_without_a_text_prefix_is_a_problem(self):
        src = body_src('    raise Stop("not in a git checkout")\n')
        exempt = {"merge:go": ("refusal-matches-rule", EXEMPT_REASON)}
        self.assertTrue(any("text prefix" in p for p in module_problems(src, exempt)))

    def test_an_exempt_prefix_no_uncited_site_starts_with_is_stale(self):
        src = body_src('    raise Stop("other text")\n')
        exempt = {"merge:go: gone text": ("refusal-matches-rule", EXEMPT_REASON)}
        self.assertTrue(any("no uncited site starts with" in p for p in module_problems(src, exempt)))

    def test_an_exempt_entry_with_a_home_and_a_reason_passes(self):
        self.assertEqual(self.problems({"bare-id": ("step-one", EXEMPT_REASON)}), [])

    def test_an_exempt_prefix_without_a_reason_is_a_problem(self):
        src = body_src('    raise Stop("not in a git checkout")\n')
        exempt = {"merge:go: not in a git checkout": "refusal-matches-rule"}
        self.assertTrue(any("needs a reason" in p for p in module_problems(src, exempt)))


# A rule that leaves CLAUDE.md for a destination file (lint/test_rule_homes.py) is still a rule: the audit reads
# the file, maps the anchor through rule_mechanisms.json, and reads a slug repeated across files as a duplicate.
MOVED = "**Ask.** Ask one question at a time, and never batch them.<!-- rule:moved-rule-under-test -->\n"
MOVED_MAP = {"rules": {**GOOD_MAP["rules"],
                       "moved-rule-under-test": {"mechanism": {"kind": "guard", "ref": "agent-model-cap"}}}}


def many_rules(n):
    return "".join("**Bulk %d.** Do thing %d.<!-- rule:bulk-rule-%d -->\n" % (i, i, i) for i in range(n))


BULK_MAP = {"rules": {**GOOD_MAP["rules"],
                      **{"bulk-rule-%d" % i: {"mechanism": {"kind": "guard", "ref": "agent-model-cap"}}
                         for i in range(30)}}}


class DestinationRuleFileTests(RuleFileTree, unittest.TestCase):

    def test_rule_files_reads_every_destination_file(self):
        listed = [p.replace(os.sep, "/") for p in rule_audit.RULE_FILES]
        self.assertIn("CLAUDE.md", listed)  # control: the file every audit has read
        self.assertEqual([p for p in test_rule_homes.DESTINATIONS if p not in listed], [],
                         "RULE_FILES does not read these destination files")

    def test_rule_moved_into_a_destination_file_is_seen_and_mapped(self):
        in_claude = self.rule_tree({"CLAUDE.md": GOOD_MD + MOVED})
        self.assertEqual(run(md=in_claude, rule_map=MOVED_MAP), [])  # control: the same rule in CLAUDE.md
        moved = self.rule_tree({"CLAUDE.md": GOOD_MD, "skills/waiting-page/SKILL.md": MOVED,
                                "skills/fresh-prose/SKILL.md": "# Fresh prose\n\nNo rule in this file.\n"})
        self.assertEqual(run(md=moved, rule_map=MOVED_MAP), [])

    def test_slug_repeated_in_a_destination_file_is_a_duplicate(self):
        for rel in test_rule_homes.DESTINATIONS:
            with self.subTest(file=rel):
                problems = run(md=self.rule_tree({"CLAUDE.md": GOOD_MD, rel: GOOD_MD}))
                self.assertTrue(any("duplicate" in p and "shared-trees-no-destructive-git" in p for p in problems),
                                problems)

    def test_every_rule_in_a_large_destination_file_is_seen(self):
        bulk = self.rule_tree({"CLAUDE.md": GOOD_MD, "skills/design-review/SKILL.md": many_rules(30)})
        self.assertEqual(run(md=bulk, rule_map=BULK_MAP), [])


if __name__ == "__main__":
    unittest.main()
