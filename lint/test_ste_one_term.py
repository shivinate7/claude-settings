#!/usr/bin/env python3
"""Tests for STE022, the warn-only one-term lint (rule speak-one-name-per-thing, step one-term-warn-lint).

STE022 reads the "Not" names from GLOSSARY.md on each run and warns when prose uses one. It is advisory:
it never fails a run (decision plain-prose-lint).

    python lint/test_ste_one_term.py -v
"""
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ste_lint  # noqa: E402


def lint(text, path="t.md"):
    return [f for f in ste_lint.Linter(dict(ste_lint.DEFAULT_CONFIG)).check_text(path, text) if f.code == "STE022"]


class OneTermTests(unittest.TestCase):
    def test_not_name_in_prose_warns(self):
        got = lint("The gate refuses the push.\n")
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0].severity, "warning")
        self.assertIn("guard", got[0].message)

    def test_glossary_term_passes(self):
        self.assertEqual(lint("The guard refuses the push.\n"), [])

    def test_plural_and_case_warn(self):
        self.assertEqual(len(lint("Gates stop the push.\n")), 1)

    def test_code_span_passes(self):
        self.assertEqual(lint("The word `gate` names a hook in another repo.\n"), [])

    def test_this_sense_name_is_left_to_the_reviewer(self):
        self.assertEqual(lint("Add an entry to the list.\n"), [])

    def test_glossary_file_itself_is_skipped(self):
        self.assertEqual(lint("The gate refuses the push.\n", path="GLOSSARY.md"), [])

    def test_source_comment_warns_and_string_passes(self):
        linter = ste_lint.Linter(dict(ste_lint.DEFAULT_CONFIG))
        code = '# The gate refuses the push.\nx = "the gate refuses"\n'
        got = [f for f in linter.check_source("t.py", code) if f.code == "STE022"]
        self.assertEqual([f.line for f in got], [1])

    def test_names_come_from_glossary_not_a_copy(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "GLOSSARY.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write("## Terms\n\n| Term | Meaning | Home | Not |\n|---|---|---|---|\n"
                        "| zork | A thing. | `GLOSSARY.md` | `blorp` |\n")
            old = ste_lint.GLOSSARY_PATH
            ste_lint.GLOSSARY_PATH = path
            try:
                self.assertEqual(len(lint("The blorp runs.\n")), 1)
                self.assertEqual(lint("The gate runs.\n"), [])
            finally:
                ste_lint.GLOSSARY_PATH = old

    def test_missing_glossary_gives_no_finding(self):
        old = ste_lint.GLOSSARY_PATH
        ste_lint.GLOSSARY_PATH = os.path.join(HERE, "no-such-glossary.md")
        try:
            self.assertEqual(lint("The gate runs.\n"), [])
        finally:
            ste_lint.GLOSSARY_PATH = old

    def test_never_fails_a_run(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.md")
            with open(p, "w", encoding="utf-8") as f:
                f.write("The gate refuses the push.\n")
            r = subprocess.run([sys.executable, os.path.join(HERE, "ste_lint.py"), p],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("STE022", r.stdout)


if __name__ == "__main__":
    unittest.main()
