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


def make_fixture(root, files=None, links=None):
    """A repo under `root` whose one commit tracks `files` (path -> text) and `links` (path -> link target, each a symlink
    entry). The default is the spec and the symlink to it. -> (repo, commit sha)."""
    if files is None:
        files = {"spec/openapi.yaml": SPEC}
    if links is None:
        links = {LINK_PATH.replace(os.sep, "/"): LINK}
    repo = os.path.join(root, "src")
    os.makedirs(repo, exist_ok=True)
    git(repo, "init", "-q")
    for rel, text in files.items():
        path = os.path.join(repo, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    if files:
        git(repo, "add", "--", *files)
    for rel, target in links.items():
        blob = git(repo, "hash-object", "-w", "--stdin", stdin=target)
        git(repo, "update-index", "--add", "--cacheinfo", "120000,%s,%s" % (blob, rel))
    git(repo, "commit", "-q", "--no-gpg-sign", "-m", "Track the fixture files and links")
    return repo, git(repo, "rev-parse", "HEAD")


def escapes(dest):
    """(path, real path) of each entry under dest whose real path lies outside dest. Links are not followed into."""
    root = os.path.realpath(dest)
    found = []
    for folder, names, files in os.walk(dest):
        for name in names + files:
            path = os.path.join(folder, name)
            real = os.path.realpath(path)
            if os.path.commonpath([root, real]) != root:
                found.append((os.path.relpath(path, dest), real))
    return found


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


SECRET = "not for the export\n"


def escape_export(name, links):
    """Export a commit that tracks `links` into dest, a folder two levels below ROOT/<name>. The secret one level above dest
    is at inner/secret.txt, and the one two levels above is at secret2.txt. -> (dest, error)."""
    base = os.path.join(ROOT, name)
    parent = os.path.join(base, "inner")
    dest = os.path.join(parent, "dest")
    os.makedirs(dest)
    for path in (os.path.join(parent, "secret.txt"), os.path.join(base, "secret2.txt")):
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(SECRET)
    repo, sha = make_fixture(base, files={}, links=links)
    return dest, tree_export.export_tree(repo, sha, dest)


class TreeExportLinkTargetCases(unittest.TestCase):
    """A link whose real path leaves the export fails the export, and the error names it. Where os.symlink is refused,
    a link to a tracked directory copies the directory's contents."""

    def assert_refused_by_name(self, dest, error, names):
        self.assertIsNotNone(error, "the export let an escaping link through and returned None")
        self.assertTrue(any(name in error for name in names),
                        "the export's error names none of the escaping links %s: %s" % (names, error))
        found = escapes(dest)
        self.assertEqual(found, [], "a link under the export still resolves outside it: %s" % found)

    def test_a_direct_link_out_of_the_export_is_refused_by_name(self):
        dest, error = escape_export("direct", {"escape-link.txt": "../secret.txt"})
        self.assert_refused_by_name(dest, error, ["escape-link.txt"])

    def test_an_absolute_link_out_of_the_export_is_refused_by_name(self):
        secret = os.path.join(ROOT, "absolute", "inner", "secret.txt")
        dest, error = escape_export("absolute", {"abs-link.txt": secret})
        self.assert_refused_by_name(dest, error, ["abs-link.txt"])

    def test_a_chain_through_a_link_to_the_export_is_refused_by_name(self):
        dest, error = escape_export("chain", {"chain-a": "chain-b/../secret.txt", "chain-b": "."})
        self.assert_refused_by_name(dest, error, ["chain-a"])

    def test_a_three_level_chain_out_of_the_export_is_refused_by_name(self):
        links = {"chain3-a": "chain3-b/../secret2.txt", "chain3-b": "chain3-c/..", "chain3-c": "."}
        dest, error = escape_export("chain3", links)
        self.assert_refused_by_name(dest, error, ["chain3-a", "chain3-b"])

    def test_a_refused_link_to_a_tracked_directory_copies_its_contents(self):
        base = os.path.join(ROOT, "dirlink")
        dest = os.path.join(base, "dest")
        os.makedirs(dest)
        repo, sha = make_fixture(base, files={"spec/openapi.yaml": SPEC}, links={"Sources/Kit/spec": "../../spec"})
        with mock.patch("os.symlink", side_effect=REFUSED):
            error = tree_export.export_tree(repo, sha, dest)
        self.assertIsNone(error, "a refused link to a tracked directory failed the export: %s" % error)
        with open(os.path.join(dest, "Sources", "Kit", "spec", "openapi.yaml"), encoding="utf-8", newline="") as handle:
            self.assertEqual(handle.read(), SPEC, "the directory's contents are not at the refused link's path")


MANIFEST_NAME = ".tree-export-paths"  # pinned here; hooks/tree_export.py MANIFEST must hold the same name
MANIFEST_FILES = {  # a space, a non-ASCII name, a nested folder, next to the default symlink
    "spec/openapi.yaml": SPEC,
    "docs/with space.md": "a\n",
    "docs/café.md": "b\n",
    "lint/deep/nested/mod.py": "c = 1\n",
}


def tracked_paths(repo, sha):
    """The paths git lists at SHA, read raw (-z) so no name is quoted, sorted."""
    env = {key: value for key, value in os.environ.items() if key not in SCRUBBED}
    done = subprocess.run(["git", "-C", repo, "ls-tree", "-r", "-z", "--name-only", sha], capture_output=True, env=env)
    if done.returncode != 0:
        raise RuntimeError("git ls-tree failed: %s" % done.stderr.decode(errors="replace").strip())
    return sorted(path.decode("utf-8") for path in done.stdout.split(b"\0") if path)


def export_manifest_fixture(name):
    """The MANIFEST_FILES fixture exported to a new folder ROOT/<name>-export. -> (the folder, the paths git lists at the sha).
    A failed export raises: it is a broken fixture, not the claim under test."""
    repo, sha = make_fixture(os.path.join(ROOT, name), files=MANIFEST_FILES)
    dest = os.path.join(ROOT, name + "-export")
    os.makedirs(dest)
    error = tree_export.export_tree(repo, sha, dest)
    if error is not None:
        raise RuntimeError("the export of the manifest fixture failed: %s" % error)
    return dest, tracked_paths(repo, sha)


def manifest_rows(dest):
    """The rows of the manifest in the copy `dest`, in order and raw, so a row written twice shows twice."""
    with open(os.path.join(dest, MANIFEST_NAME), encoding="utf-8", newline="") as handle:
        return [line for line in handle.read().split("\n") if line]


class TreeExportManifestCases(unittest.TestCase):
    """The export writes a manifest at its root: one archived path per line, the same set git lists at the commit."""

    def test_the_export_writes_a_manifest_of_the_paths_git_lists_at_the_sha(self):
        repo, sha = make_fixture(os.path.join(ROOT, "names"), files=MANIFEST_FILES)
        want = tracked_paths(repo, sha)
        dest = os.path.join(ROOT, "names-export")
        os.makedirs(dest)
        error = tree_export.export_tree(repo, sha, dest)
        self.assertIsNone(error, "the export of the manifest fixture failed: %s" % error)
        name = getattr(tree_export, "MANIFEST", None)
        self.assertEqual(name, MANIFEST_NAME, "hooks/tree_export.py names no MANIFEST of %s, it is %r" % (MANIFEST_NAME, name))
        path = os.path.join(dest, MANIFEST_NAME)
        self.assertTrue(os.path.isfile(path), "the export wrote no manifest at %s" % MANIFEST_NAME)
        with open(path, encoding="utf-8", newline="") as handle:
            got = sorted(line for line in handle.read().split("\n") if line)
        self.assertEqual(got, want, "the manifest lists %s, git lists %s at the sha" % (got, want))

    def test_manifest_add_puts_an_added_path_in_the_copys_manifest_and_keeps_the_rest(self):
        dest, listed = export_manifest_fixture("add")
        want = listed + ["lint/zz_new.py"]
        add = getattr(tree_export, "manifest_add", None)
        self.assertTrue(callable(add), "hooks/tree_export.py has no manifest_add(dest, paths): an --add file never reaches the copy's manifest")
        add(dest, ["lint/zz_new.py"])
        got = sorted(manifest_rows(dest))
        self.assertEqual(got, sorted(want), "manifest_add left the copy's manifest as %s, want the export's paths and lint/zz_new.py" % (got,))

    def test_manifest_add_writes_a_path_already_listed_or_given_twice_once(self):
        dest, listed = export_manifest_fixture("dedupe")
        already = listed[0]  # a path the export already listed
        self.assertEqual(manifest_rows(dest).count(already), 1, "the export should list %s once before the add" % already)
        add = getattr(tree_export, "manifest_add", None)
        self.assertTrue(callable(add), "hooks/tree_export.py has no manifest_add(dest, paths)")
        add(dest, [already, "lint/zz_twice.py", "lint/zz_twice.py"])
        rows = manifest_rows(dest)
        self.assertEqual(rows.count(already), 1, "manifest_add wrote %s again: the manifest lists it %d times, want 1" % (already, rows.count(already)))
        self.assertEqual(rows.count("lint/zz_twice.py"), 1, "manifest_add wrote lint/zz_twice.py %d times for one path given twice, want 1" % rows.count("lint/zz_twice.py"))


class TreeExportPathCases(unittest.TestCase):
    """A tracked path the one-path-per-line manifest cannot hold fails the export, and the error names the path."""

    def test_a_path_with_a_newline_fails_the_export_and_names_the_path(self):
        try:
            repo, sha = make_fixture(os.path.join(ROOT, "newline"), files={"docs/two\nlines.md": "a\n"})
        except (OSError, subprocess.CalledProcessError) as exc:
            self.skipTest("the file system or git refuses a newline in a name: %s" % exc)
        dest = os.path.join(ROOT, "newline-export")
        os.makedirs(dest)
        error = tree_export.export_tree(repo, sha, dest)
        self.assertIsNotNone(error, "the export returned None for a path with a newline, so the copy drops the file with no error")
        self.assertIn("docs/two", error, "the export's error names no path: %s" % error)

    def test_manifest_add_refuses_a_path_with_a_newline_and_names_it(self):
        dest, _ = export_manifest_fixture("add-newline")
        add = getattr(tree_export, "manifest_add", None)
        self.assertTrue(callable(add), "hooks/tree_export.py has no manifest_add(dest, paths)")
        with self.assertRaises(ValueError, msg="manifest_add listed a path with a newline and raised nothing") as caught:
            add(dest, ["docs/two\nlines.md"])
        self.assertIn("docs/two", str(caught.exception), "manifest_add's error names no part of the path: %s" % caught.exception)


if __name__ == "__main__":
    unittest.main()
