#!/usr/bin/env python3
"""Cases for hooks/tree_export.py (`export_tree`): what an export of a commit that tracks a symlink leaves in a folder.

    python3 hooks/test_tree_export.py

The fixture commit tracks `spec/openapi.yaml` and `Sources/Kit/openapi.yaml`, a symlink to `../../spec/openapi.yaml`.
The link is a symlink entry in the index (`git update-index --cacheinfo 120000`), so the fixture builds where
os.symlink is refused. The archive lists the link before its target, so the export meets the link first.
Standard library only.
"""
import os
import subprocess
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "lint"))
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
sys.path.insert(0, os.path.join(REPO, "testing"))
import tracked_tree  # noqa: E402  rm_tree clears the read-only bit of git objects (testing/tracked_tree.py)
import tree_export  # noqa: E402  the one home of the export (hooks/tree_export.py)

ROOT = _test_temp.run_folder()
SPEC = "openapi: 3.0.3\ninfo:\n  title: Kit\n"
LINK = "../../spec/openapi.yaml"
LINK_PATH = os.path.join("Sources", "Kit", "openapi.yaml")
REFUSED = OSError(1, "symlink refused: no symlink privilege")
SCRUBBED = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES")
SRC = None
SHA = None


def git(repo, *args, stdin=None):
    """One git call in the fixture repo. Raises RuntimeError on a nonzero exit: a broken fixture is not a red case."""
    env = {key: value for key, value in os.environ.items() if key not in SCRUBBED}
    for key, value in (("GIT_AUTHOR_NAME", "fixture"), ("GIT_AUTHOR_EMAIL", "fixture@example.invalid"),
                       ("GIT_COMMITTER_NAME", "fixture"), ("GIT_COMMITTER_EMAIL", "fixture@example.invalid")):
        env.setdefault(key, value)
    done = subprocess.run(["git", "-C", repo] + list(args), input=stdin, capture_output=True, text=True, env=env)
    if done.returncode != 0:
        raise RuntimeError("git %s failed: %s" % (args[0], done.stderr.strip()))
    return done.stdout.strip()


def make_fixture(root):
    """A repo whose one commit tracks the spec and the symlink to it. -> (repo, commit sha)."""
    repo = os.path.join(root, "src")
    os.makedirs(os.path.join(repo, "spec"))
    git(repo, "init", "-q")
    with open(os.path.join(repo, "spec", "openapi.yaml"), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(SPEC)
    git(repo, "add", "spec/openapi.yaml")
    blob = git(repo, "hash-object", "-w", "--stdin", stdin=LINK)
    git(repo, "update-index", "--add", "--cacheinfo", "120000,%s,%s" % (blob, LINK_PATH.replace(os.sep, "/")))
    git(repo, "commit", "-q", "--no-gpg-sign", "-m", "Track the spec and a symlink to it")
    return repo, git(repo, "rev-parse", "HEAD")


def setUpModule():
    global SRC, SHA
    SRC, SHA = make_fixture(ROOT)


def tearDownModule():
    tracked_tree.rm_tree(ROOT)  # test-temp-standard: teardown removes the run folder


class TreeExportSymlinkCases(unittest.TestCase):
    """A commit that tracks a symlink: the export keeps the link, and a host that refuses os.symlink still gets the target's text."""

    def export(self, name):
        """Export the fixture commit into a fresh folder. -> (folder, error), error None when the export worked."""
        dest = os.path.join(ROOT, name)
        os.makedirs(dest)
        return dest, tree_export.export_tree(SRC, SHA, dest)

    def read(self, path):
        with open(path, encoding="utf-8", newline="") as handle:
            return handle.read()

    def test_a_tracked_relative_symlink_stays_a_link_in_the_export(self):
        dest, error = self.export("kept")
        self.assertIsNone(error, "the export of a commit with a tracked symlink failed: %s" % error)
        link = os.path.join(dest, LINK_PATH)
        self.assertTrue(os.path.islink(link), "the tracked symlink is missing from the export")
        self.assertEqual(os.readlink(link), LINK, "the exported link does not point at the tracked target")
        self.assertEqual(self.read(link), SPEC, "reading the exported link does not give the target's text")

    def test_a_refused_symlink_leaves_the_target_text_at_its_path(self):
        with mock.patch("os.symlink", side_effect=REFUSED):
            dest, error = self.export("refused")
        self.assertIsNone(error, "a refused symlink failed the whole export: %s" % error)
        link = os.path.join(dest, LINK_PATH)
        self.assertTrue(os.path.exists(link), "a refused symlink left nothing at its path in the export")
        self.assertEqual(self.read(link), SPEC, "the file at a refused symlink's path does not hold the target's text")

    def test_a_refused_symlink_does_not_fail_the_other_files(self):
        with mock.patch("os.symlink", side_effect=REFUSED):
            dest, error = self.export("refused-other")
        self.assertIsNone(error, "a refused symlink failed the whole export: %s" % error)
        self.assertEqual(self.read(os.path.join(dest, "spec", "openapi.yaml")), SPEC,
                         "the other file did not export where os.symlink is refused")


if __name__ == "__main__":
    unittest.main()
