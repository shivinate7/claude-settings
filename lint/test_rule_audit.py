#!/usr/bin/env python3
"""Fixture tests for rule_audit.py.

Each test builds a small CLAUDE.md fragment, a map, and (when it matters) a guard.py or
gates.yml fragment in memory, then calls `check(...)` directly. No subprocess: the audit
itself does not touch the transcript or the hook protocol the way ste_gate/report_gate do.

Run with:

    python3 lint/test_rule_audit.py -v
"""
import os
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
    refuse(tool, "ask", "subagent-model-cap", REASON, matched)
    record(tool, "noted", "merge-main", matched)
'''

WORKFLOW_SRC = '''
jobs:
  gates:
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


def run(md=GOOD_MD, rule_map=None, guard=GUARD_SRC, workflow=WORKFLOW_SRC,
        rule_floor=1, unmechanized_expected=None):
    """Call check() with small pins sized to the fixture, not this repo's real numbers."""
    if rule_map is None:
        rule_map = GOOD_MAP
    if unmechanized_expected is None:
        rules = rule_map.get("rules", {})
        unmechanized_expected = sum(
            1 for r in rules.values()
            if isinstance(r, dict) and (r.get("mechanism") or {}).get("kind") == "unmechanized"
        )
    return rule_audit.check(md, rule_map, guard, workflow, rule_floor, unmechanized_expected)


def gate_map(mechanism):
    mechanism = dict(mechanism, kind="gate")
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
                    "mechanism": {"kind": "guard", "ref": "subagent-model-cap"}
                }
            }
        }
        problems = run(rule_map=rule_map)
        self.assertEqual(problems, [])

    def test_row_naming_a_missing_gate_file_fails(self):
        rule_map = {
            "rules": {
                "shared-trees-no-destructive-git": {
                    "mechanism": {"kind": "gate", "ref": "lint/does_not_exist.py"}
                }
            }
        }
        problems = run(rule_map=rule_map)
        self.assertTrue(any("does_not_exist.py" in p for p in problems), problems)

    def test_row_citing_a_needle_is_refused(self):
        # The old shape: a real file and a substring that is present. It must go red now.
        rule_map = gate_map({"ref": "lint/rule_audit.py", "needle": "every rule anchor maps"})
        problems = run(rule_map=rule_map)
        self.assertTrue(any("needle" in p for p in problems), problems)

    def test_gate_row_with_no_test_and_no_setting_is_refused(self):
        problems = run(rule_map=gate_map({"ref": "lint/rule_audit.py"}))
        self.assertTrue(any("proves nothing" in p for p in problems), problems)

    def test_gate_row_citing_a_real_test_passes(self):
        problems = run(rule_map=gate_map({
            "ref": "lint/rule_audit.py",
            "test": "lint/test_rule_audit.py::RuleAuditTests.test_single_mapped_rule_is_clean"}))
        self.assertEqual(problems, [])

    def test_gate_row_citing_a_test_that_does_not_exist_fails(self):
        problems = run(rule_map=gate_map({
            "ref": "lint/rule_audit.py",
            "test": "lint/test_rule_audit.py::RuleAuditTests.test_no_such_thing"}))
        self.assertTrue(any("does not resolve" in p for p in problems), problems)

    def test_gate_row_citing_a_docstring_phrase_as_a_test_fails(self):
        problems = run(rule_map=gate_map({
            "ref": "hooks/test_guard.py",
            "test": "hooks/test_guard.py::drives the guard as Claude Code drives it"}))
        self.assertTrue(any("does not resolve" in p for p in problems), problems)

    def test_gate_row_with_a_setting_that_holds_passes(self):
        problems = run(rule_map=gate_map({
            "ref": "settings.json",
            "setting": {"file": "settings.json", "path": "env.CLAUDE_CODE_SUBAGENT_MODEL",
                        "equals": "sonnet"}}))
        self.assertEqual(problems, [])

    def test_gate_row_with_a_wrong_setting_value_fails(self):
        # The name is present in settings.json; only the value is wrong.
        problems = run(rule_map=gate_map({
            "ref": "settings.json",
            "setting": {"file": "settings.json", "path": "env.CLAUDE_CODE_SUBAGENT_MODEL",
                        "equals": "opus"}}))
        self.assertTrue(any("does not hold" in p for p in problems), problems)

    def test_gate_row_with_a_setting_name_absent_fails(self):
        problems = run(rule_map=gate_map({
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

SIBLING_MAP = {
    "rules": {
        "shared-trees-no-destructive-git": {"mechanism": {"kind": "guard", "ref": "sibling-rule"}}
    }
}


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
        problems = rule_audit.check(GOOD_MD, SIBLING_MAP, guard_text, "", 1, 0)
        self.assertEqual(problems, [])

    def test_guard_py_alone_leaves_that_sibling_rule_stale(self):
        """Control: the same fixture read the old way (guard.py only) must read red, so the
        case above proves the reader, not the fixture."""
        root = self.tree(self.files())
        guard_text = rule_audit.read(os.path.join(root, "hooks", "guard.py"))
        problems = rule_audit.check(GOOD_MD, SIBLING_MAP, guard_text, "", 1, 0)
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
            for rel, body in (("gate.py", "x = 1\n"), ("test_other.py", "import os\n"),
                              ("test_gate.py", "import gate\n"),
                              ("test_run.py", "import subprocess\nsubprocess.run(['python3', 'lint/gate.py'])\n"),
                              ("test_mention.py", "NOTE = 'lint/gate.py'\n")):
                with open(os.path.join(root, rel), "w", encoding="utf-8") as f:
                    f.write(body)
            self.assertIn("proves nothing",
                          rule_audit.link_problem("test_other.py::t", "lint/gate.py", root))
            self.assertIsNone(rule_audit.link_problem("test_gate.py::t", "lint/gate.py", root))
            self.assertIsNone(rule_audit.link_problem("test_run.py::t", "lint/gate.py", root))
            self.assertIn("proves nothing",
                          rule_audit.link_problem("test_mention.py::t", "lint/gate.py", root))
            self.assertIsNone(rule_audit.link_problem("gate.py::t", "gate.py", root))

    def test_row_whose_test_never_touches_its_ref_fails(self):
        problems = run(rule_map=gate_map({
            "ref": "lint/report_gate.py",
            "test": "lint/test_rule_audit.py::RuleAuditTests.test_single_mapped_rule_is_clean"}))
        self.assertTrue(any("unlinked" in p for p in problems), problems)

    def test_missing_file_is_red(self):
        self.assertIn("does not exist",
                      rule_audit.citation_problem("nope.py::x", tempfile.gettempdir()))


if __name__ == "__main__":
    unittest.main()
