#!/usr/bin/env python3
"""Fixture suite for the fixture-copy helpers: testing/tracked_tree.py, testing/tracked_tree.sh and
testing/TrackedTree.ps1. Each case builds a throwaway git repo and asks a helper what it copies.

Red cases: a new module a lane has not yet added, an ignored file, a suite, a file gone from the
checkout, a folder git lists nothing in, and a root that is no repo. The shell and PowerShell helpers
must copy the same set as the Python one. pwsh missing skips the PowerShell case here and fails it in CI.
ManifestCases: an exported copy (no .git) lists by the manifest its export wrote at its root.
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
sys.path.insert(0, HERE)
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
TESTING = os.path.join(HERE, "..", "testing")
sys.path.insert(0, TESTING)
import tracked_tree  # noqa: E402
import tree_export  # noqa: E402  the export whose manifest ManifestCases list (hooks/tree_export.py)

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
        tracked_tree.rm_tree(self.tree)
        self.assertFalse(os.path.exists(self.tree))

    def test_handler_clears_the_bit_before_the_retry(self):
        # Bites on any OS and as root, where a read-only file still unlinks and the case above proves nothing.
        path = os.path.join(self.tree, "objects", "pack")
        with open(path, "w") as f:
            f.write("x")
        os.chmod(path, stat.S_IREAD)
        seen = []

        def func(p):
            seen.append(bool(os.stat(p).st_mode & stat.S_IWRITE))
            os.unlink(p)
        tracked_tree.clear_readonly(func, path, None)
        self.assertEqual(seen, [True])
        self.assertFalse(os.path.exists(path))

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


MANIFEST_NAME = ".tree-export-paths"  # pinned here; hooks/tree_export.py MANIFEST must hold the same name (ManifestCases pins it)
GIT_STATE = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES")
CLEAN = {  # the one commit ManifestCases exports: a space, a non-ASCII name, a nested folder, a suite, a plain module
    "lint/check_a.py": "import shared\n",
    "lint/shared.py": "X = 1\n",
    "lint/data/kinds.json": "{}\n",
    "lint/test_check_a.py": "suite\n",
    "lint/with space.py": "Z = 3\n",
    "lint/café.py": "W = 4\n",
}
RUN_FOLDER = None  # made in setUpModule, so an import leaks no folder
CLEAN_REPO = None  # the fixture repo of CLEAN, built in setUpModule
CLEAN_SHA = None


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def git_clean(root, *args):
    """One git call in the ManifestCases fixture. A nonzero exit raises: a broken fixture is an error, not a red case."""
    env = {key: value for key, value in ENV.items() if key not in GIT_STATE}
    done = subprocess.run(["git", "-C", root, *args], capture_output=True, env=env)
    if done.returncode != 0:
        raise RuntimeError("git %s failed: %s" % (args[0], done.stderr.decode(errors="replace").strip()))
    return done.stdout.decode("utf-8").strip()


def setUpModule():
    global RUN_FOLDER, CLEAN_REPO, CLEAN_SHA
    RUN_FOLDER = _test_temp.run_folder()
    CLEAN_REPO = os.path.join(RUN_FOLDER, "clean")
    os.makedirs(CLEAN_REPO)
    for rel, text in CLEAN.items():
        write(os.path.join(CLEAN_REPO, *rel.split("/")), text)
    git_clean(CLEAN_REPO, "init", "-q")
    git_clean(CLEAN_REPO, "add", "-A")
    git_clean(CLEAN_REPO, "commit", "-q", "-m", "Track the clean fixture")
    CLEAN_SHA = git_clean(CLEAN_REPO, "rev-parse", "HEAD")


def tearDownModule():
    tracked_tree.rm_tree(RUN_FOLDER)  # test-temp-standard: teardown removes the run folder


class ManifestCases(unittest.TestCase):
    """An exported copy has no .git. Its root's manifest lists it, and a root with neither fails loudly and names both."""

    def setUp(self):
        self.case = tempfile.mkdtemp(dir=RUN_FOLDER)  # one folder per case, under this run's folder
        tracked_tree._listing.cache_clear()
        self.addCleanup(tracked_tree._listing.cache_clear)

    def export(self, name):
        """Export CLEAN_SHA into a fresh folder. Scope first: the copy holds no .git in it or above, so a case reads the copy."""
        dest = os.path.join(self.case, name)
        os.makedirs(dest)
        error = tree_export.export_tree(CLEAN_REPO, CLEAN_SHA, dest)
        self.assertIsNone(error, "the export of the clean fixture failed: %s" % error)
        folder = os.path.realpath(dest)
        while True:
            self.assertFalse(os.path.lexists(os.path.join(folder, ".git")), "a .git sits in or above the copy, at %s" % folder)
            parent = os.path.dirname(folder)
            if parent == folder:
                return dest
            folder = parent

    def listed(self, call, what):
        """The helper's answer, or a FAIL that names the cause: the helper raised on a copy it should list."""
        try:
            return call()
        except RuntimeError as exc:
            self.fail("tracked_tree could not list %s: %s" % (what, exc))

    def test_tracked_lists_an_exported_copy_as_the_checkout_at_the_sha_lists_it(self):
        dest = self.export("listing")
        want = tracked_tree.tracked("lint", CLEAN_REPO)
        got = self.listed(lambda: tracked_tree.tracked("lint", dest), "the exported copy's lint/")
        self.assertEqual(got, want, "the exported copy lists %s, the checkout at the sha lists %s" % (got, want))

    def test_copy_tracked_copies_into_an_exported_copy_the_paths_the_checkout_copies(self):
        dest = self.export("copying")
        want = tracked_tree.copy_tracked(os.path.join(self.case, "want"), "lint", root=CLEAN_REPO)
        got = self.listed(lambda: tracked_tree.copy_tracked(os.path.join(self.case, "got"), "lint", root=dest),
                          "the exported copy's lint/")
        self.assertEqual(got, want, "the exported copy copies %s, the checkout copies %s" % (got, want))

    def test_read_tracked_reads_from_an_exported_copy_the_text_the_checkout_reads(self):
        dest = self.export("reading")
        want = tracked_tree.read_tracked("lint", root=CLEAN_REPO)
        got = self.listed(lambda: tracked_tree.read_tracked("lint", root=dest), "the exported copy's lint/")
        self.assertEqual(got, want, "the exported copy reads other text than the checkout at the sha")

    def test_the_export_writes_the_manifest_at_the_copy_root_and_copy_tracked_does_not_take_it(self):
        dest = self.export("manifest")
        self.assertTrue(os.path.isfile(os.path.join(dest, MANIFEST_NAME)), "the export wrote no %s at the copy root" % MANIFEST_NAME)
        copied = self.listed(lambda: tracked_tree.copy_tracked(os.path.join(self.case, "again"), "lint", root=dest),
                             "the exported copy's lint/")
        self.assertNotIn(MANIFEST_NAME, [os.path.basename(path) for path in copied], "the manifest is a copied file: %s" % copied)

    def test_a_root_with_no_git_and_no_manifest_fails_loudly_and_names_both(self):
        plain = os.path.join(self.case, "plain")
        write(os.path.join(plain, "lint", "check_a.py"), "X = 1\n")
        with self.assertRaises(RuntimeError) as caught:
            tracked_tree.tracked("lint", plain)
        message = str(caught.exception)
        self.assertIn(".git", message, "the error names no .git folder: %s" % message)
        self.assertIn(MANIFEST_NAME, message, "the error names no %s manifest: %s" % (MANIFEST_NAME, message))

    def test_a_hand_written_manifest_lists_its_paths_in_a_tree_with_no_git(self):
        tree = os.path.join(self.case, "hand")
        for rel in ("lint/check_a.py", "lint/shared.py", "lint/data/kinds.json", "lint/test_check_a.py"):
            write(os.path.join(tree, *rel.split("/")), "x\n")
        write(os.path.join(tree, MANIFEST_NAME),
              "lint/check_a.py\nlint/shared.py\nlint/data/kinds.json\nlint/test_check_a.py\nlint/gone.py\n")
        got = self.listed(lambda: tracked_tree.tracked("lint", tree), "a tree with a manifest and no .git")
        self.assertEqual(got, ["check_a.py", "data/kinds.json", "shared.py"],
                         "the manifest's lint/ paths list as %s" % got)

    def test_a_manifest_with_no_file_under_the_folder_fails_and_names_the_manifest(self):
        tree = os.path.join(self.case, "empty")
        write(os.path.join(tree, "hooks", "a.py"), "x\n")
        write(os.path.join(tree, MANIFEST_NAME), "hooks/a.py\n")
        with self.assertRaises(RuntimeError) as caught:
            tracked_tree.tracked("lint", tree)
        self.assertIn(MANIFEST_NAME, str(caught.exception), "the error for a manifest with no lint/ file names no manifest")


if __name__ == "__main__":
    unittest.main()
