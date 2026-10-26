#!/usr/bin/env python3
"""Cases for lint/check_claude_md_size.py. Standard library only.

    python3 lint/test_check_claude_md_size.py

The check warns when a CLAUDE.md passes 200 lines. A warning never fails: it exits 0, because a
warning that fails CI is a false alarm. A missing file is a skip. Each case writes its files to a
temp tree and runs the real script there. CLAUDE_MD_SIZE_UNDER_TEST overrides the module path.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE = os.environ.get("CLAUDE_MD_SIZE_UNDER_TEST") or os.path.join(HERE, "check_claude_md_size.py")
DOC = "https://code.claude.com/docs/en/memory"


def lines(n):
    return "".join("line %d\n" % i for i in range(n))


class ClaudeMdSizeTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(os.path.isfile(MODULE), "module absent: lint/check_claude_md_size.py")
        self.tree = tempfile.mkdtemp(prefix="cms_")

    def tearDown(self):
        shutil.rmtree(self.tree)

    def write(self, rel, text):
        path = os.path.join(self.tree, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

    def run_check(self, *args):
        return subprocess.run([sys.executable, MODULE, *args], cwd=self.tree,
                              capture_output=True, text=True, timeout=30)

    def test_201_lines_warns_and_exits_0(self):
        self.write("CLAUDE.md", lines(201))
        r = self.run_check("CLAUDE.md")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("WARN", r.stdout)
        self.assertIn("201 lines", r.stdout)
        self.assertIn(DOC, r.stdout)

    def test_200_lines_does_not_warn(self):
        self.write("CLAUDE.md", lines(200))
        r = self.run_check("CLAUDE.md")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("WARN", r.stdout)

    def test_last_line_without_newline_counts(self):
        self.write("CLAUDE.md", lines(200) + "one more")
        r = self.run_check("CLAUDE.md")
        self.assertIn("201 lines", r.stdout)

    def test_missing_file_is_a_skip(self):
        r = self.run_check("CLAUDE.md")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("skip", r.stdout)
        self.assertNotIn("WARN", r.stdout)

    def test_default_reads_both_repo_files(self):
        self.write("CLAUDE.md", lines(10))
        self.write(os.path.join(".claude", "CLAUDE.md"), lines(250))
        r = self.run_check()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(".claude/CLAUDE.md: 250 lines", r.stdout.replace("\\", "/"))
        self.assertEqual(r.stdout.count("WARN"), 1)

    def test_warning_names_the_read_deny_rule(self):
        self.write("CLAUDE.md", lines(300))
        r = self.run_check("CLAUDE.md")
        self.assertIn("Read deny", r.stdout)

    def test_unknown_option_is_refused(self):
        r = self.run_check("--fix")
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
