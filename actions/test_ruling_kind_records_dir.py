#!/usr/bin/env python3
"""Cases for actions/ruling-kind: the records-dir input and how check.sh passes it on.

    python3 actions/test_ruling_kind_records_dir.py

The action checks the records folder named by its records-dir input. The input defaults to "",
and then the lint takes the decisions folder from lint/layout.json. Stdlib only, so action.yml is
read as text, not parsed as YAML. Shape only: test_action.sh runs the action end to end.
The CheckShRecordsDir cases run check.sh itself in a fixture repo, with RECORDS_DIR set or unset.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lint"))
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import tracked_tree  # noqa: E402  copies what git lists, so no fixture lists files (testing/tracked_tree.py)
ACTION = os.path.join(HERE, "ruling-kind")
ACTION_YML = os.path.join(ACTION, "action.yml")
CHECK_SH = os.path.join(ACTION, "check.sh")
ENV_MAP = re.compile(r"^\s+([A-Z][A-Z0-9_]*):\s*\$\{\{\s*inputs\.records-dir\s*\}\}\s*$", re.M)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def input_block(text, name):
    """The lines under `inputs:` -> `  <name>:`, or None. Stops at the next key of the same level."""
    lines = text.split("\n")
    if "inputs:" not in lines:
        return None
    body = []
    for line in lines[lines.index("inputs:") + 1:]:
        if line.strip() and not line.startswith(" "):
            break
        body.append(line)
    start = next((i for i, line in enumerate(body) if re.match(r"^  %s:\s*$" % re.escape(name), line)), None)
    if start is None:
        return None
    block = []
    for line in body[start + 1:]:
        if line.strip() and not line.startswith("    "):
            break
        block.append(line)
    return "\n".join(block)


class RecordsDirInput(unittest.TestCase):
    def test_records_dir_input_defaults_to_the_layout(self):
        block = input_block(read(ACTION_YML), "records-dir")
        self.assertIsNotNone(block, "action.yml has no inputs.records-dir")
        m = re.search(r"^\s+default:\s*['\"]?([^'\"\s]*)['\"]?\s*$", block, re.M)
        self.assertIsNotNone(m, "inputs.records-dir has no default")
        self.assertEqual(m.group(1), "")

    def test_check_sh_passes_the_records_dir_to_the_lint(self):
        m = ENV_MAP.search(read(ACTION_YML))
        self.assertIsNotNone(m, "no step env line maps inputs.records-dir to a variable")
        name = m.group(1)
        lint_lines = [line for line in read(CHECK_SH).split("\n")
                      if "check_ruling_kind.py" in line and not line.lstrip().startswith("#")]
        self.assertTrue(lint_lines, "check.sh does not run check_ruling_kind.py")
        # Always --dir, so the lint refuses a folder that does not exist; an empty value is first
        # resolved through lint/layout.py.
        flag = re.compile(r"--dir\s+\"?\$\{?%s\}?\"?(?=\s|$)" % re.escape(name))
        self.assertTrue(any(flag.search(line) for line in lint_lines),
                        "the lint call in check.sh does not pass --dir \"$%s\"" % name)
        self.assertRegex(read(CHECK_SH), r"%s=\"\$\(python3 \S*lint/layout\.py\" path " % re.escape(name))


GIT = ["git", "-c", "user.name=test", "-c", "user.email=test@example.com"]
BASH = shutil.which("bash")


@unittest.skipUnless(BASH, "needs bash to run check.sh")
class CheckShRecordsDir(unittest.TestCase):
    """check.sh names the records folder through RECORDS_DIR. A bad folder is red, never green."""

    def setUp(self):
        self.tree = tempfile.mkdtemp(prefix="rdir_")
        self.addCleanup(tracked_tree.rm_tree, self.tree)
        self.put("README.md", "# Home\n")  # the Home of the valid record below
        self.put("decisions/base-ruling.md", "Old ruling, no kind line. Not in the diff.\n")
        self.git("init", "-q", "-b", "main")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "base")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")  # the base, with no fetch
        self.git("switch", "-q", "-c", "topic")
        self.put("decisions/new-ruling.md", "Kind: process\nHome: README.md\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "topic")

    def put(self, rel, text):
        path = os.path.join(self.tree, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

    def git(self, *args):
        subprocess.run(GIT + list(args), cwd=self.tree, check=True, capture_output=True, text=True)

    def check(self, records_dir=None):
        """Run check.sh. RECORDS_DIR is unset when records_dir is None, else set to it, even if empty."""
        env = dict(os.environ, BASE_REF="main")
        env.pop("RECORDS_DIR", None)
        if records_dir is not None:
            env["RECORDS_DIR"] = records_dir
        r = subprocess.run([BASH, CHECK_SH], cwd=self.tree, env=env,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        return r.returncode, r.stdout + r.stderr

    def test_unset_records_dir_checks_decisions(self):
        rc, out = self.check()
        self.assertEqual(rc, 0, out)

    def test_empty_records_dir_reads_the_layout(self):
        # Empty is the action's default: no --dir, so the lint judges the layout's folder.
        self.put("decisions/bad-ruling.md", "No kind line.\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "bad")
        rc, out = self.check("")
        self.assertEqual(rc, 1, out)
        self.assertIn("decisions/bad-ruling.md", out)

    def test_default_folder_that_does_not_exist_is_red(self):
        # A repo with no decisions folder where the layout reads it: red, as an explicit bad folder is.
        self.git("mv", "decisions", "notes")
        self.git("commit", "-q", "-m", "move")
        rc, out = self.check()
        self.assertNotEqual(rc, 0, out)
        self.assertIn("'decisions'", out)

    def test_explicit_decisions_passes(self):
        rc, out = self.check("decisions")
        self.assertEqual(rc, 0, out)

    def test_unusable_records_dir_fails_and_names_it(self):
        for value in ("decision", "docs/decisions-old", ".", "Decisions"):
            with self.subTest(records_dir=value):
                rc, out = self.check(value)
                self.assertNotEqual(rc, 0, out)
                self.assertIn("'%s'" % value, out)
                self.assertNotIn("Traceback", out)

    def test_records_dir_that_names_a_file_fails_and_names_it(self):
        for value in ("README.md", "decisions/base-ruling.md"):  # both files exist in the fixture
            with self.subTest(records_dir=value):
                rc, out = self.check(value)
                self.assertNotEqual(rc, 0, out)
                self.assertIn("'%s'" % value, out)
                self.assertNotIn("Traceback", out)


if __name__ == "__main__":
    unittest.main()
