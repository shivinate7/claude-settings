#!/usr/bin/env python3
"""Fixture suite for the fixture-copy helpers: testing/tracked_tree.py, testing/tracked_tree.sh and
testing/TrackedTree.ps1. Each case builds a throwaway git repo and asks a helper what it copies.

Red cases: a new module a lane has not yet added, an ignored file, a suite, a file gone from the
checkout, a folder git lists nothing in, and a root that is no repo. The shell and PowerShell helpers
must copy the same set as the Python one. pwsh missing skips the PowerShell case here and fails it in CI.
Run: python3 lint/test_tracked_tree.py
"""
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
TESTING = os.path.join(HERE, "..", "testing")
sys.path.insert(0, TESTING)
import tracked_tree  # noqa: E402

ENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull, GIT_AUTHOR_NAME="t",
           GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")


def listing(folder):
    out = []
    for base, _dirs, files in os.walk(folder):
        out += [os.path.relpath(os.path.join(base, f), folder).replace(os.sep, "/") for f in files]
    return sorted(out)


class Repo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ttree_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = os.path.join(self.tmp, "repo")
        os.makedirs(self.root)
        self.git("init", "-q", "-b", "main")
        self.put("lint/check_a.py", "import shared\n")
        self.put("lint/shared.py", "X = 1\n")
        self.put("lint/data/kinds.json", "{}\n")
        self.put("lint/test_check_a.py", "suite\n")
        self.put("lint/check_a_test.py", "suite\n")
        self.put("lint/a.test.mjs", "suite\n")
        self.put("lint/gone.py", "X = 2\n")
        self.put(".gitignore", "*.log\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "base")
        os.remove(os.path.join(self.root, "lint", "gone.py"))  # listed by git, gone from the checkout
        self.put("lint/new_shared.py", "Y = 1\n")  # a lane's new module, not yet added
        self.put("lint/run.log", "noise\n")  # ignored
        self.dest = os.path.join(self.tmp, "dest")

    WANT = ["check_a.py", "data/kinds.json", "new_shared.py", "shared.py"]

    def git(self, *args):
        subprocess.run(["git", "-C", self.root, *args], check=True, capture_output=True, env=ENV)

    def put(self, rel, text):
        path = os.path.join(self.root, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)


class PythonHelper(Repo):
    def test_the_set_is_tracked_plus_new_minus_ignored_suites_and_gone(self):
        self.assertEqual(tracked_tree.tracked("lint", self.root), self.WANT)

    def test_copy_tracked_lands_the_set_under_the_folder(self):
        got = tracked_tree.copy_tracked(self.dest, "lint", root=self.root)
        self.assertEqual(got, ["lint/" + n for n in self.WANT])
        self.assertEqual(listing(self.dest), ["lint/" + n for n in self.WANT])

    def test_copy_folder_lands_flat_and_skip_leaves_a_path_out(self):
        tracked_tree.copy_folder("lint", self.dest, self.root, skip=("shared.py",))
        self.assertEqual(listing(self.dest), [n for n in self.WANT if n != "shared.py"])

    def test_read_tracked_gives_the_bytes_as_they_are(self):
        self.put("lint/crlf.py", "a = 1\r\n")
        got = tracked_tree.read_tracked("lint", root=self.root)
        self.assertEqual(got["lint/crlf.py"], "a = 1\r\n")
        self.assertEqual(sorted(got), sorted(["lint/" + n for n in self.WANT] + ["lint/crlf.py"]))

    @unittest.skipIf(os.name == "nt", "no executable bit on Windows")
    def test_the_mode_is_kept(self):
        path = os.path.join(self.root, "lint", "shared.py")
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
        tracked_tree.copy_folder("lint", self.dest, self.root)
        self.assertTrue(os.stat(os.path.join(self.dest, "shared.py")).st_mode & stat.S_IXUSR)

    def test_an_empty_folder_raises(self):
        os.makedirs(os.path.join(self.root, "empty"))
        with self.assertRaises(RuntimeError):
            tracked_tree.tracked("empty", self.root)

    def test_a_root_that_is_no_repo_raises(self):
        plain = os.path.join(self.tmp, "plain")
        os.makedirs(os.path.join(plain, "lint"))
        with open(os.path.join(plain, "lint", "x.py"), "w") as f:
            f.write("x\n")
        with self.assertRaises(RuntimeError):
            tracked_tree.tracked("lint", plain)


class ShellHelper(Repo):
    def sh(self, *call):
        script = '. "$1"; shift; TRACKED_ROOT=$1; shift; "$@"'
        return subprocess.run(["sh", "-c", script, "sh", os.path.join(TESTING, "tracked_tree.sh"), self.root, *call],
                              capture_output=True, text=True, env=ENV)

    @unittest.skipUnless(shutil.which("sh"), "no POSIX sh")
    def test_copy_tracked_copies_the_python_set(self):
        done = self.sh("copy_tracked", self.dest, "lint")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(listing(self.dest), ["lint/" + n for n in self.WANT])

    @unittest.skipUnless(shutil.which("sh"), "no POSIX sh")
    def test_copy_folder_lands_flat_with_a_skip(self):
        done = self.sh("copy_folder", "lint", self.dest, "shared.py")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(listing(self.dest), [n for n in self.WANT if n != "shared.py"])

    @unittest.skipUnless(shutil.which("sh"), "no POSIX sh")
    def test_an_empty_folder_fails(self):
        os.makedirs(os.path.join(self.root, "empty"))
        done = self.sh("copy_tracked", self.dest, "empty")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("lists no file", done.stderr)


class PowerShellHelper(Repo):
    def test_copy_tracked_copies_the_python_set(self):
        pwsh = shutil.which("pwsh") or shutil.which("powershell")
        if not pwsh:
            if os.environ.get("CI"):
                self.fail("no pwsh in CI: a skip here would pass the PowerShell helper unrun")
            self.skipTest("no pwsh")
        script = ". '%s'; Copy-Tracked -Root '%s' -DestRoot '%s' -Folders @('lint') | Out-Null" % (
            os.path.join(TESTING, "TrackedTree.ps1"), self.root, self.dest)
        done = subprocess.run([pwsh, "-NoProfile", "-NonInteractive", "-Command", script],
                              capture_output=True, text=True, env=ENV)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(listing(self.dest), ["lint/" + n for n in self.WANT])


class RmTree(unittest.TestCase):
    """tracked_tree.rm_tree: the one folder-removal helper of every fixture suite."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rmtree_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.tree = os.path.join(self.tmp, "tree")
        os.makedirs(os.path.join(self.tree, "objects"))

    def test_removes_a_tree_holding_a_read_only_file(self):
        # Red on the old handler's absence; on Windows the file is why a bare rmtree fails.
        path = os.path.join(self.tree, "objects", "pack")
        with open(path, "w") as f:
            f.write("x")
        os.chmod(path, stat.S_IREAD)
        os.chmod(os.path.join(self.tree, "objects"), stat.S_IREAD | stat.S_IEXEC)  # POSIX: unlink needs write here
        tracked_tree.rm_tree(self.tree)
        self.assertFalse(os.path.exists(self.tree))

    def test_a_file_that_vanishes_mid_delete_does_not_raise(self):
        path = os.path.join(self.tree, "objects", "pack")
        with open(path, "w") as f:
            f.write("x")
        os.unlink(path)  # gone before the handler's chmod
        tracked_tree.clear_readonly(os.unlink, path, None)  # the retry's own FileNotFoundError also stays quiet
        real = os.chmod
        with open(path, "w") as f:
            f.write("x")

        def vanish(p, mode):
            os.unlink(p)
            return real(p, mode)  # raises FileNotFoundError, as chmod does on a file removed under it
        with mock.patch("os.chmod", vanish):
            tracked_tree.clear_readonly(os.unlink, path, None)
        tracked_tree.rm_tree(self.tree)
        self.assertFalse(os.path.exists(self.tree))


if __name__ == "__main__":
    unittest.main()
