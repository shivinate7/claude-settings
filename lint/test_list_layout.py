#!/usr/bin/env python3
"""Layout of the lists many lanes add to: the case arms of .github/scripts/ci-scope.sh and the parenthesised
import tuples of hooks/guard.py. Each entry sits on its own line and the entries are sorted in plain byte order, so
two lanes conflict only when they edit the same entry.

The case reader is testing/bash_case.py. The scanner cases pin it on the traps a bash line holds: a `|` inside a
quote or a `$(...)`, a `#` inside a word, a lone quote in a comment, a multi-line quoted text, a nested case.

Run with:  python3 lint/test_list_layout.py -v
"""
import ast
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import bash_case  # noqa: E402  the one home of the case reader

REPO = os.path.join(HERE, "..")
SCOPE_SCRIPT = os.path.join(REPO, ".github", "scripts", "ci-scope.sh")
GUARD = os.path.join(REPO, "hooks", "guard.py")


def byte_order(items):
    return sorted(items, key=lambda s: s.encode("utf-8"))


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class ScannerReadsStrings(unittest.TestCase):
    """Green controls for the case reader: each snippet holds one trap, and the reader must not fall into it."""

    def alts(self, src):
        return [[text for text, _ in arm["alts"]] for arm in bash_case.case_arms(src)]

    def test_pipe_inside_quotes_or_command_substitution_is_no_separator(self):
        src = 'case "$f" in\n  "a|b"|c) x=1 ;;\n  $(echo "d|e")|f) x=2 ;;\nesac\n'
        self.assertEqual(self.alts(src), [['"a|b"', "c"], ['$(echo "d|e")', "f"]])

    def test_hash_inside_a_word_is_text_not_a_comment(self):
        src = 'case "$f" in\n  a#b|c#) x=1 ;;\n  *) ;;\nesac\n'
        self.assertEqual(self.alts(src), [["a#b", "c#"], ["*"]])

    def test_comment_with_a_lone_quote_opens_no_string(self):
        src = "case $f in\n  # don't read this quote\n  a) x=1 ;;\n  # case z in\nesac\n"
        self.assertEqual(self.alts(src), [["a"]])

    def test_comment_openers_and_esac_inside_quotes_stay_text(self):
        src = 'case $f in\n  a) x="/* // #"; y=\';;\' ;;\n  b) z="esac" ;;\nesac\n'
        self.assertEqual(self.alts(src), [["a"], ["b"]])

    def test_multi_line_double_quoted_text_is_one_word(self):
        src = 'case $f in\n  a) x="one\n  esac ;; two\n  b) ;;\n" ;;\n  c) ;;\nesac\n'
        arms = bash_case.case_arms(src)
        self.assertEqual([[text for text, _ in arm["alts"]] for arm in arms], [["a"], ["c"]])
        self.assertEqual(arms[1]["line"], 6, "the arm after the quoted text starts on line 6")

    def test_backslash_newline_joins_alternatives_each_on_its_own_line(self):
        src = "case $f in\n  a|\\\n  b|\\\n  c) ;;\nesac\n"
        self.assertEqual(bash_case.case_arms(src)[0]["alts"], [("a", 2), ("b", 3), ("c", 4)])

    def test_nested_case_is_listed_after_its_outer_arm_with_the_outer_alternatives(self):
        src = "case $f in\n  x) case $g in\n    y|z) ;; esac ;;\n  *) ;;\nesac\n"
        arms = bash_case.case_arms(src)
        self.assertEqual([[text for text, _ in arm["alts"]] for arm in arms], [["x"], ["y", "z"], ["*"]])
        self.assertEqual(arms[1]["outer"], (("x",),))
        self.assertEqual(arms[2]["outer"], ())

    def test_arithmetic_and_process_substitution_are_one_word_each(self):
        src = 'n=$((n + 1))\nwhile read x; do :; done < <(printf "a)\\n")\ncase $f in\n  a) ;;\nesac\n'
        self.assertEqual(self.alts(src), [["a"]])

    def test_empty_case_has_no_arm(self):
        self.assertEqual(bash_case.case_arms("case $f in esac\n"), [])

    def test_unclosed_case_is_a_read_error_not_a_quiet_empty_list(self):
        with self.assertRaises(bash_case.ReadError):
            bash_case.case_arms("case $f in\n  a) x=1 ;;\n")


class CaseArmsOfCiScope(unittest.TestCase):
    """The case arms of .github/scripts/ci-scope.sh, nested ones included."""

    @classmethod
    def setUpClass(cls):
        cls.arms = bash_case.case_arms(read(SCOPE_SCRIPT))

    def test_scope_finds_the_case_arms_and_the_guard_arm(self):
        self.assertGreaterEqual(len(self.arms), 60, "the reader found fewer case arms than the script holds")
        texts = [[text for text, _ in arm["alts"]] for arm in self.arms]
        self.assertTrue(any("hooks/guard.py" in alts for alts in texts), "no arm holds hooks/guard.py")

    def test_each_arm_holds_at_most_one_alternative_per_line(self):
        crowded = []
        for arm in self.arms:
            lines = [line for _, line in arm["alts"]]
            if len(set(lines)) != len(lines):
                crowded.append(arm["line"])
        self.assertEqual(crowded, [], "arms with two alternatives on one line, at these first lines")

    def test_alternatives_within_an_arm_are_sorted_in_byte_order(self):
        unsorted = []
        for arm in self.arms:
            texts = [text for text, _ in arm["alts"]]
            if texts != byte_order(texts):
                unsorted.append(arm["line"])
        self.assertEqual(unsorted, [], "arms whose alternatives are out of byte order, at these first lines")


class ImportTuplesOfGuard(unittest.TestCase):
    """The parenthesised `from ... import (...)` tuples of hooks/guard.py: those that span more than one line."""

    @classmethod
    def setUpClass(cls):
        tree = ast.parse(read(GUARD))
        cls.tuples = [node for node in ast.walk(tree)
                      if isinstance(node, ast.ImportFrom) and node.end_lineno > node.lineno]

    def test_scope_finds_the_multi_line_import_tuples(self):
        modules = [node.module for node in self.tuples]
        self.assertIn("guard_core", modules, "the guard_core import tuple was not found")
        self.assertGreaterEqual(len(self.tuples), 2)

    def test_each_name_in_an_import_tuple_sits_on_its_own_line(self):
        crowded = []
        for node in self.tuples:
            lines = [alias.lineno for alias in node.names]
            if len(set(lines)) != len(lines):
                crowded.append("%s (line %d)" % (node.module, node.lineno))
        self.assertEqual(crowded, [], "import tuples with two names on one line")

    def test_names_in_an_import_tuple_are_sorted_in_byte_order(self):
        unsorted = []
        for node in self.tuples:
            names = [alias.name for alias in node.names]
            if names != byte_order(names):
                unsorted.append("%s (line %d)" % (node.module, node.lineno))
        self.assertEqual(unsorted, [], "import tuples whose names are out of byte order")


if __name__ == "__main__":
    unittest.main()
