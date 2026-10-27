#!/usr/bin/env python3
"""Cases for skills/project-ops/scripts/scaffold.py. Standard library only.

    python3 skills/project-ops/tests/test_scaffold.py

Each case runs the scaffold into an empty temp folder, the dry run of the skill. The cases prove
the file list, the filled placeholders, the refusal over an existing file, and that nothing the
skill writes or ships names this project's threads, sessions or people.
"""
import contextlib
import io
import os
import re
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(SKILL, "scripts"))
import scaffold  # noqa: E402

EXPECTED = [
    "CLAUDE.md",
    "roadmap/README.md",
    "roadmap/outbox/README.md",
    "roadmap/data/steps/.gitkeep",
    "roadmap/data/topics/.gitkeep",
    "roadmap/data/meta/.gitkeep",
    "briefs/.gitkeep",
    "handoffs/.gitkeep",
]
# A claude.ai thread or session id, the owner's names, and the live page of this project.
PRIVATE = re.compile(r"cmsg_|session_[0-9A-Za-z]{8}|shiv|R3iCpK91QRjC5he8bwfY7m", re.IGNORECASE)


def run(*args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = scaffold.main(list(args))
    return code, out.getvalue(), err.getvalue()


def tree(root):
    found = {}
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in files:
            path = os.path.join(base, name)
            with open(path, encoding="utf-8") as f:
                found[os.path.relpath(path, root).replace(os.sep, "/")] = f.read()
    return found


class Scaffold(unittest.TestCase):
    def setUp(self):
        self.dest = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dest)

    def test_writes_the_skeleton(self):
        code, out, err = run("--dest", self.dest, "--repo", "acme/widgets")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.split(), EXPECTED)
        self.assertEqual(sorted(tree(self.dest)), sorted(EXPECTED))

    def test_fills_the_placeholders(self):
        run("--dest", self.dest, "--repo", "acme/widgets", "--branch", "record")
        files = tree(self.dest)
        self.assertIn("acme/widgets, branch `record`", files["CLAUDE.md"])
        for rel, text in files.items():
            self.assertNotIn("{{", text, rel)

    def test_readme_points_at_the_roadmap_skill(self):
        run("--dest", self.dest, "--repo", "acme/widgets")
        readme = tree(self.dest)["roadmap/README.md"]
        self.assertIn("skills/roadmap", readme)
        self.assertIn("--live", readme)
        self.assertNotIn("build.py` on the", readme)
        self.assertNotIn("has no page", readme)

    def test_skill_files_name_no_stale_builder(self):
        for rel, text in tree(SKILL).items():
            if rel.startswith("tests/"):
                continue
            self.assertNotRegex(text, r"(?<!skills/)roadmap/build\.py", rel)
            self.assertNotIn("has no page", text, rel)

    def test_triage_passes_live_at_each_publish(self):
        text = tree(SKILL)["templates/operating-model.md"]
        self.assertRegex(text, r"(?s)publishes the roadmap page.*--live")

    def test_writes_nothing_private(self):
        run("--dest", self.dest, "--repo", "acme/widgets")
        for rel, text in tree(self.dest).items():
            self.assertIsNone(PRIVATE.search(text), rel)

    def test_ships_nothing_private(self):
        for rel, text in tree(SKILL).items():
            if rel.startswith("tests/"):
                continue
            self.assertIsNone(PRIVATE.search(text), rel)

    def test_refuses_over_an_existing_file(self):
        with open(os.path.join(self.dest, "CLAUDE.md"), "w", encoding="utf-8") as f:
            f.write("mine\n")
        code, out, err = run("--dest", self.dest, "--repo", "acme/widgets")
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("CLAUDE.md", err)
        self.assertEqual(tree(self.dest), {"CLAUDE.md": "mine\n"})

    def test_failed_write_leaves_no_files(self):
        # A file named like a folder the scaffold makes fails the write after earlier files land.
        with open(os.path.join(self.dest, "briefs"), "w", encoding="utf-8") as f:
            f.write("x")
        code, out, err = run("--dest", self.dest, "--repo", "acme/widgets")
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("write failed", err)
        self.assertEqual(tree(self.dest), {"briefs": "x"})

    def test_second_run_changes_nothing(self):
        run("--dest", self.dest, "--repo", "acme/widgets")
        before = tree(self.dest)
        code, _, _ = run("--dest", self.dest, "--repo", "acme/widgets")
        self.assertEqual(code, 1)
        self.assertEqual(tree(self.dest), before)

    def test_bad_arguments(self):
        self.assertEqual(run("--dest", self.dest, "--repo", "widgets")[0], 2)
        self.assertEqual(run("--dest", self.dest, "--repo", "a/b", "--branch", "x y")[0], 2)
        self.assertEqual(run("--dest", os.path.join(self.dest, "none"), "--repo", "a/b")[0], 2)
        self.assertEqual(tree(self.dest), {})


if __name__ == "__main__":
    unittest.main()
