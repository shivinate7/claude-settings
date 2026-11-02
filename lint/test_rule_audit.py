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
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rule_audit  # noqa: E402

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


class RuleAuditTests(unittest.TestCase):

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
        """Write both RULE_FILES under a temp root and read them back through rule_text()."""
        root = tempfile.mkdtemp()
        for rel, body in zip(rule_audit.RULE_FILES, (claude_md, style_md)):
            path = os.path.join(root, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(body)
        return rule_audit.rule_text(root)

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
            "ref": "lint/report_guard.py",
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
# id with a site that prints no cite, or whose reason the scan cannot read, fails unless it is in
# REFUSAL_UNCITED_EXEMPT with its home. The exempt list only shrinks.

CITE_RE = re.compile(r"\b(decision|rule) ([a-z0-9][a-z0-9-]*)\b")
HOME_RE = re.compile(r"[a-z0-9][a-z0-9-]*")
MAX_DEPTH = 12
PENDING_ASK = "PENDING_ASK"  # filled only by ask_command(), whose literal call sites are scanned

# Refusal id -> its home (a step slug or debt id), for an id that still prints no cite. The
# refusal-vs-rule record gives the uncited rule rewrites to refusal-uncited-rewrites, agent-model-cap
# to refusal-looser-fixes, and the rest to the sweep step refusal-matches-rule.
REFUSAL_UNCITED_EXEMPT = {
    "gh-login-switch": "refusal-uncited-rewrites",
    "handoff-unread": "refusal-uncited-rewrites",
    "merge-role-proof": "refusal-uncited-rewrites",
    "option-letter-keys": "refusal-uncited-rewrites",
    "question-departs": "refusal-uncited-rewrites",
    "rework-off-page": "refusal-uncited-rewrites",
    "trust-card-in-build": "refusal-uncited-rewrites",
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
    # merge/merge.py stops, keyed `merge:<function>` for the function that raises them. Each stop reports
    # a failed git or gh step or a config fault, and its message names no decision or rule.
    "merge:Host.base_state": "refusal-matches-rule",  # the base state is unreadable; the stop carries gh's output
    "merge:Host.gh": "refusal-matches-rule",  # gh failed on a network error, after its retries
    "merge:Host.merge": "refusal-matches-rule",  # the merge call's outcome is unknown, not this run's, or still OPEN
    "merge:Host.pages": "refusal-matches-rule",  # a repo file could not be read from GitHub
    "merge:Host.pr": "refusal-matches-rule",  # the pull request could not be read
    "merge:Host.pr_number": "refusal-matches-rule",  # no pull request is named, or the head matches several
    "merge:Host.runs": "refusal-matches-rule",  # gh run list failed
    "merge:base_job_caps": "refusal-matches-rule",  # a workflow file could not be read on the base
    "merge:base_stamp_config": "refusal-matches-rule",  # the stamp config could not be read on the base
    "merge:base_workflows": "refusal-matches-rule",  # the workflow folder could not be listed on the base
    "merge:fail": "refusal-matches-rule",  # a failed run's stop; its text is the caller's `why`
    "merge:ff_main": "refusal-matches-rule",  # local main cannot move: fetch failed, or the commit is off origin
    "merge:host_default_branch": "refusal-matches-rule",  # the default branch cannot be read from gh
    "merge:ignore_checks": "refusal-matches-rule",  # a merge.ignoreChecks entry has no name or no reason
    "merge:keep": "refusal-matches-rule",  # a merge commit landed and stays on the branch
    "merge:lint_steps": "refusal-matches-rule",  # the lint steps cannot be listed
    "merge:load_config": "refusal-matches-rule",  # the merge config on the base is unreadable or invalid
    "merge:main": "refusal-matches-rule",  # the run is not in a git checkout
    "merge:open_worktree": "refusal-matches-rule",  # the worktree cannot open: fetch failed, branch moved, or add failed
    "merge:prove": "refusal-matches-rule",  # the fetch of the base failed after its retries
    "merge:push_branch": "refusal-matches-rule",  # the push of the branch was refused
    "merge:refuse_bad_pr": "refusal-matches-rule",  # the pull request is closed or conflicting
}


def cite_homes(root=rule_audit.ROOT):
    """-> (decision slugs, rule anchors), read from the repo as it is now."""
    decisions_dir = os.path.join(root, "docs", "decisions")
    decisions = {name[:-3] for name in os.listdir(decisions_dir) if name.endswith(".md")}
    anchors = set(rule_audit.claude_md_anchors(rule_audit.read(os.path.join(root, "CLAUDE.md"))))
    for path in glob.glob(os.path.join(root, "output-styles", "*.md")):
        anchors.update(rule_audit.claude_md_anchors(rule_audit.read(path)))
    return decisions, anchors


def cites(text, homes):
    decisions, anchors = homes
    return any(slug in (decisions if kind == "decision" else anchors) for kind, slug in CITE_RE.findall(text))


def _own(node):
    """The nodes that run in `node`'s own scope: not the bodies of the functions or classes it defines."""
    stack = list(ast.iter_child_nodes(node))
    while stack:
        child = stack.pop()
        yield child
        if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            stack.extend(ast.iter_child_nodes(child))


def _bound_names(target):
    return [n.id for n in ast.walk(target) if isinstance(n, ast.Name)]


def _locals(fdef):
    """name -> [(value, slot)] for each binding in a function. A value of None is a binding made at
    run time (an argument, a loop target), so the name has no static text. A slot is the position
    in a tuple value that the name unpacks."""
    locs = {}
    args = fdef.args
    for arg in args.posonlyargs + args.args + args.kwonlyargs + [a for a in (args.vararg, args.kwarg) if a]:
        locs.setdefault(arg.arg, []).append((None, None))
    for node in _own(fdef):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    locs.setdefault(target.id, []).append((node.value, None))
                elif isinstance(target, ast.Tuple) and all(isinstance(e, ast.Name) for e in target.elts):
                    for i, e in enumerate(target.elts):
                        locs.setdefault(e.id, []).append((node.value, i))
                else:
                    for name in _bound_names(target):
                        locs.setdefault(name, []).append((None, None))
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension, ast.AugAssign, ast.AnnAssign, ast.NamedExpr)):
            for name in _bound_names(node.target):
                locs.setdefault(name, []).append((None, None))
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                for name in _bound_names(item.optional_vars) if item.optional_vars else []:
                    locs.setdefault(name, []).append((None, None))
    return locs


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


class _Reasons:
    """The static text a reason expression can take, followed across the modules in `world`.
    -> a list with one string per branch, or None when some piece is known only at run time."""

    def __init__(self, world):
        self.world = world
        self._locals = {}

    def locals_of(self, fdef):
        if id(fdef) not in self._locals:
            self._locals[id(fdef)] = _locals(fdef)
        return self._locals[id(fdef)]

    def alts(self, expr, mod, locs, depth=0):
        if depth > MAX_DEPTH:
            return None
        d = depth + 1
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
            left, right = self.alts(expr.left, mod, locs, d), self.alts(expr.right, mod, locs, d)
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
            return self._name(expr.id, mod, locs, d, None)
        if isinstance(expr, ast.Subscript):
            if isinstance(expr.slice, ast.Constant) and isinstance(expr.slice.value, int) and expr.slice.value >= 0:
                return self._elt(expr.value, expr.slice.value, mod, locs, d)  # `reason[0]` of a tuple-valued name
            return self._dict(expr, mod, locs, d)
        if isinstance(expr, ast.Call):
            if isinstance(expr.func, ast.Attribute) and expr.func.attr == "format":
                return self.alts(expr.func.value, mod, locs, d)
            options = _dict_get_options(expr)
            if options is not None:
                return _union([self.alts(o, mod, locs, d) for o in options])
            return self._call(expr, mod, locs, d, None)
        return None

    def _static_branches(self, name, mod, locs, depth):
        """The static text of a local name's branches, skipping the run-time ones. `x = x or "text"` adds
        "text": its `x` is the run-time branch that another binding holds."""
        found = []
        for value, slot in locs.get(name, []):
            if isinstance(value, ast.BoolOp) and isinstance(value.op, ast.Or) \
                    and isinstance(value.values[0], ast.Name) and value.values[0].id == name:
                parts = [self.alts(v, mod, locs, depth) for v in value.values[1:]]
            elif value is not None and slot is None:
                parts = [self.alts(value, mod, locs, depth)]
            else:
                parts = []
            found += [t for part in parts for t in (part or [])]
        return found

    def _value(self, value, slot, index, mod, locs, depth):
        if slot is not None:
            return self._elt(value, slot, mod, locs, depth)
        if index is not None:
            return self._elt(value, index, mod, locs, depth)
        return self.alts(value, mod, locs, depth)

    def _elt(self, expr, i, mod, locs, depth):
        """The text of element `i` of a tuple-valued expression."""
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
            return self._name(expr.id, mod, locs, d, i)
        return None

    def _name(self, name, mod, locs, depth, index):
        if name in locs:
            return _union([self._value(v, slot, index, mod, locs, depth) if v is not None else None
                           for v, slot in locs[name]])
        home = self._home(mod, name)
        if home is None:
            return None
        hmod, values = home
        return _union([self._value(v, None, index, hmod, {}, depth) for v in values])

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
        """The reason a call returns: each return value, or element `index` of each return tuple."""
        if not isinstance(call.func, ast.Name) or depth > MAX_DEPTH:
            return None
        found = self._function(call.func.id, mod)
        if found is None:
            return None
        fmod, fdef = found
        flocs = self.locals_of(fdef)
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
                return self.alts(value, hmod, {}, depth + 1)
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
    name = call.func.id if isinstance(call.func, ast.Name) else getattr(call.func, "attr", "")
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
               for v, _ in bound):
            return []  # the ask_command() call sites carry these ids
        for value, slot in bound:
            options = _tuple_options(value) if slot == 0 else None
            if options and all(len(t.elts) == 2 and isinstance(t.elts[0], ast.Constant) for t in options):
                return [(t.elts[0].value, t.elts[1]) for t in options]
    unattributed.append(where)
    return []


def _raw_refuse_reason(node):
    """The `permissionDecisionReason` expression of a dict literal that prints a deny or an ask, else None.
    A dict whose decision is a variable is guard_core.refuse() itself, which the calls to it cover."""
    if not isinstance(node, ast.Dict):
        return None
    keys = {k.value: v for k, v in zip(node.keys, node.values) if isinstance(k, ast.Constant)}
    decision = keys.get("permissionDecision")
    if isinstance(decision, ast.Constant) and decision.value in ("deny", "ask"):
        return keys.get("permissionDecisionReason")
    return None


def _stop_classes(mod):
    """The names of the exception classes of a module that stops its run: `Stop` and each class that
    derives from one. Empty when the module defines no `Stop`."""
    classes = [n for n in mod.tree.body if isinstance(n, ast.ClassDef)]
    names = {"Stop"} if any(c.name == "Stop" for c in classes) else set()
    grown = True
    while grown:
        grown = False
        for c in classes:
            if c.name not in names and any(isinstance(b, ast.Name) and b.id in names for b in c.bases):
                names.add(c.name)
                grown = True
    return names


def _stop_reason(node, stops):
    """The message expression of `raise Stop(...)`, also as `raise (A if c else B)(...)`, else None."""
    if not (isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call) and node.exc.args):
        return None
    func = node.exc.func
    named = [n.id for n in ast.walk(func) if isinstance(n, ast.Name)] if isinstance(func, (ast.Name, ast.IfExp)) else []
    return node.exc.args[0] if named and all(n in stops for n in named) else None


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


def refusal_status(sources, homes, scope, guards=None):
    """-> (statuses, unattributed). statuses: refusal id -> [(where, status)], where a `file:line`
    and status `cited`, `no cite` or `not resolved`. `sources` maps each module name to its text;
    `scope` names the modules whose refusals count, and `guards` the guard modules among them (all of
    `scope` when None). A guard module's refuse() and ask_command() calls name their id. Any module in
    scope also counts a raw deny dict and a `raise Stop(...)` of its own; their id is `module:function`,
    as they name none. A hook that is no guard module (a judge hook) prints its deny in its own
    refuse(), so only that print counts there, not its call of guard_core.refuse(). unattributed: the
    calls whose id the scan cannot read."""
    world = {name: _Module(name, text) for name, text in sources.items()}
    reasons = _Reasons(world)
    statuses, unattributed = {}, []
    guards = scope if guards is None else guards
    for mod in world.values():
        if mod.name not in scope:
            continue
        stops, qualified = _stop_classes(mod), _qualified_names(mod.tree)
        scopes = [(mod.tree, {}, "<module>")] + [(n, reasons.locals_of(n), qualified.get(id(n), n.name))
                                                 for n in ast.walk(mod.tree) if isinstance(n, ast.FunctionDef)]
        for node, locs, func in scopes:
            for site in _own(node):
                where = "%s.py:%d" % (mod.name, site.lineno) if hasattr(site, "lineno") else ""
                found = []
                if isinstance(site, ast.Call) and mod.name in guards:
                    found = _refusals_of(site, locs, where, unattributed, mod, reasons)
                else:
                    expr = _raw_refuse_reason(site) or _stop_reason(site, stops)
                    if expr is not None:
                        found = [("%s:%s" % (mod.name, func), expr)]
                for rid, expr in found:
                    text = reasons.alts(expr, mod, locs)
                    if not text:
                        status = "not resolved"
                    elif all(cites(t, homes) for t in text):
                        status = "cited"
                    else:
                        status = "no cite"
                    statuses.setdefault(rid, []).append((where, status))
    for rows in statuses.values():
        rows.sort(key=lambda row: (row[0].rsplit(":", 1)[0], int(row[0].rsplit(":", 1)[1])))
    return statuses, unattributed


def refusal_problems(sources, homes, exempt, scope, emitted=None, guards=None):
    """The ratchet's problems, one line each. Empty when every refusal id cites or is exempt."""
    statuses, unattributed = refusal_status(sources, homes, scope, guards)
    problems = ["%s: refuse() or ask_command() id is not a string literal the scan can read" % w
                for w in unattributed]
    if emitted is not None:
        problems += ["%s: refusal id is not in rule_audit.emitted_rule_ids" % rid
                     for rid in sorted(r for r in set(statuses) - emitted if ":" not in r)]  # `module:function` ids are no guard.log ids
    failing = {rid: [(w, s) for w, s in rows if s != "cited"] for rid, rows in statuses.items()}
    failing = {rid: rows for rid, rows in failing.items() if rows}
    for rid in sorted(failing):
        if rid not in exempt:
            problems.append("%s: %s" % (rid, "; ".join("%s %s" % row for row in failing[rid])))
    for rid, home in sorted(exempt.items()):
        if rid not in statuses:
            problems.append("%s: remove from exempt; no refusal prints it" % rid)
        elif rid not in failing:
            problems.append("%s: remove from exempt; every site now cites" % rid)
        if not HOME_RE.fullmatch(home):
            problems.append("%s: exempt home `%s` is not a step slug or debt id" % (rid, home))
    return problems


def _hooks_world():
    """The text of every hooks module but the tests, and the merge tool. The scan reads all of them, so a
    judge hook or a new module that prints a refusal is in scope with no list of its own."""
    paths = glob.glob(os.path.join(rule_audit.ROOT, "hooks", "*.py")) + [os.path.join(rule_audit.ROOT, "merge", "merge.py")]
    return {os.path.splitext(os.path.basename(p))[0]: rule_audit.read(p)
            for p in paths if not os.path.basename(p).startswith("test_")}


def _guard_names():
    """The guard modules, by the same glob as rule_audit.guard_paths: their refuse() and ask_command()
    calls are sites. Other modules count only their own raw deny dicts and `raise Stop(...)`."""
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
                self.assertTrue(HOME_RE.fullmatch(REFUSAL_UNCITED_EXEMPT[rid]))


HOMES = ({"alpha"}, {"anchor-one"})
SCOPE = {"guard"}


def status_of(src, rid, extra=None, homes=HOMES):
    sources = dict(extra or {}, guard=src)
    statuses, _ = refusal_status(sources, homes, SCOPE)
    return [s for _, s in statuses.get(rid, [])]


def unattributed_of(src):
    return refusal_status({"guard": src}, HOMES, SCOPE)[1]


def site_problems(module, src):
    """The ratchet's problems for one module's source, with no exempt list and no emitted check."""
    return refusal_problems({module: src}, HOMES, {}, {module})


def uncited_site(problems, module):
    """True when a problem names a site in `module` whose reason prints no cite."""
    return any("%s.py:" % module in p and "no cite" in p for p in problems)


CRASH_REASON = ("guard-crash: the guard is missing a part and cannot judge this call.\n"
                "Remedy: reinstall, don't retry # or /* or // here.")


def raw_refuse_src(reason):
    """A JSON deny printed straight to stdout: the shape of the guard-crash deny in hooks/guard.py."""
    return ('def crash():\n'
            '    print(json.dumps({"hookSpecificOutput": {\n'
            '        "hookEventName": "PreToolUse", "permissionDecision": "deny",\n'
            '        "permissionDecisionReason": """%s"""}}))\n'
            '    sys.exit(0)\n' % reason)


JUDGE_SHAPES = (("blind_brief", "    sys.exit(0)"), ("call_judge", "    return 0"),
                ("prose_judge", "    return 0"), ("sendmessage_state", "    return 0"))


def judge_src(prefix, exit_line, fallback=None):
    """A judge hook's refuse(): a constant prefix, an optional fallback reason, then a JSON deny printed
    with exit 0. The shape of hooks/blind_brief.py, call_judge.py, prose_judge.py and sendmessage_state.py."""
    lines = ['PREFIX = "%s"' % prefix, "def refuse(payload, tool, reason):"]
    if fallback:
        lines.append('    reason = reason or "%s"' % fallback)
    lines += ['    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",',
              '                                             "permissionDecision": "deny",',
              '                                             "permissionDecisionReason": PREFIX + reason}}))',
              exit_line]
    return "\n".join(lines) + "\n"


def merge_src(raise_line):
    """The stop classes of merge/merge.py, then one function that runs `raise_line`."""
    return ('class Stop(Exception):\n    """A refusal."""\n'
            'class NetStop(Stop):\n    """A network error."""\n'
            'class Dropped(Stop):\n    """A dropped line."""\n'
            'class Held(Stop):\n    pass\n'
            'LOCK_CITE = "(decision alpha, one run holds the merge lock)"\n'
            'def go(b):\n'
            '    %s\n' % raise_line)


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
        self.assertEqual([s for _, s in statuses["call-id"]], ["no cite"])

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


if __name__ == "__main__":
    unittest.main()
