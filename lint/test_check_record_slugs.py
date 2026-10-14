#!/usr/bin/env python3
"""Cases for lint/check_record_slugs.py. Standard library only.

    python3 lint/test_check_record_slugs.py

A record file that a change adds must have a slug of 32 characters or fewer. With no flag the
check reads decisions/, deferred/ and debts/. `--dir FOLDER` points it at another folder instead, as
lint/check_ruling_kind.py does. A folder that cannot be read fails closed.

Each case builds a temp tree: a copy of the module, and the records it checks. It runs the real
script from that tree. The diff cases also make a temp git repo and set refs/remotes/origin/main,
the base the script diffs against. RECORD_SLUGS_UNDER_TEST overrides the module path.
"""
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE = os.environ.get("RECORD_SLUGS_UNDER_TEST") or os.path.join(HERE, "check_record_slugs.py")

OK = "a" * 32 + ".md"  # a slug of 32 characters passes
LONG = "a" * 33 + ".md"  # a slug of 33 characters fails
DOCS = "docs/decisions"  # a repo whose records live here passes --dir DOCS
LOOKALIKE_SIBLING = "docs/decisionsX"  # a folder that starts with the word
LOOKALIKE_WORD = "docs/notdecisions"  # a folder that only contains the word


def flagged(out):
    """The paths the check named as FAIL: each FAIL line ends with its path."""
    return [line.rsplit(" ", 1)[1] for line in out.splitlines()
            if line.startswith("check_record_slugs: FAIL:")]


def rm_tree(path):
    def clear(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)  # git objects are read-only on Windows
        func(p)
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=clear)
    else:
        shutil.rmtree(path, onerror=clear)


class RecordSlugsTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(os.path.isfile(MODULE), "module absent: lint/check_record_slugs.py")
        self.tree = tempfile.mkdtemp(prefix="rsl_")
        self.addCleanup(rm_tree, self.tree)
        os.makedirs(os.path.join(self.tree, "lint"))
        shutil.copyfile(MODULE, os.path.join(self.tree, "lint", "check_record_slugs.py"))

    def put(self, rel, text="# Record\n"):
        path = os.path.join(self.tree, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

    def lint(self, *args):
        env = dict(os.environ)
        env.pop("CI", None)  # CI turns an unknown diff into red; these cases run locally
        cmd = [sys.executable, os.path.join(self.tree, "lint", "check_record_slugs.py"), *args]
        r = subprocess.run(cmd, cwd=self.tree, env=env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        return r.returncode, r.stdout + r.stderr

    def assert_passes(self, *args):
        rc, out = self.lint(*args)
        self.assertEqual(rc, 0, out)
        self.assertNotIn("FAIL", out)

    def git(self, *args):
        subprocess.run(["git", "-C", self.tree, "-c", "user.name=test",
                        "-c", "user.email=test@example.com", "-c", "commit.gpgsign=false", *args],
                       check=True, capture_output=True, text=True)

    def commit_base(self):
        # The base is origin/main. The script diffs HEAD against it, so no branch is needed.
        self.git("init", "-q")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "base")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")

    def commit_change(self):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "change")

    # Positive controls first: a red case means nothing if the clean case fails.

    def test_default_passes_a_short_slug_in_decisions(self):
        self.put("decisions/" + OK)
        self.assert_passes("decisions/" + OK)

    def test_default_flags_long_slugs_in_decisions_and_deferred(self):
        self.put("decisions/" + LONG)
        self.put("deferred/" + LONG)
        rc, out = self.lint("decisions/" + LONG, "deferred/" + LONG)
        self.assertEqual(rc, 1, out)
        self.assertEqual(flagged(out), ["decisions/" + LONG, "deferred/" + LONG])

    def test_default_flags_long_slugs_in_debts(self):
        # debts/ holds slug-named records too, so the default run checks it with decisions/ and deferred/.
        self.put("debts/" + OK)
        self.assert_passes("debts/" + OK)
        self.put("debts/" + LONG)
        rc, out = self.lint("debts/" + LONG)
        self.assertEqual(rc, 1, out)
        self.assertEqual(flagged(out), ["debts/" + LONG])

    def test_default_leaves_other_folders_unchecked(self):
        self.put(DOCS + "/" + LONG)
        self.assert_passes(DOCS + "/" + LONG)

    def test_dir_passes_a_short_slug_in_the_named_folder(self):
        self.put(DOCS + "/" + OK)
        self.assert_passes("--dir", DOCS, DOCS + "/" + OK)

    def test_dir_flags_a_long_slug_in_the_named_folder(self):
        self.put(DOCS + "/" + LONG)
        rc, out = self.lint("--dir", DOCS, DOCS + "/" + LONG)
        self.assertEqual(rc, 1, out)
        self.assertEqual(flagged(out), [DOCS + "/" + LONG])

    def test_dir_replaces_the_default_folders(self):
        # --dir points the check at one folder. decisions/ is no longer read, as with check_ruling_kind.
        self.put(DOCS + "/" + OK)  # the named folder must exist, or --dir fails closed
        self.put("decisions/" + LONG)
        self.assert_passes("--dir", DOCS, "decisions/" + LONG)

    def test_dir_ignores_folders_that_only_look_like_it(self):
        self.put(DOCS + "/" + OK)  # the named folder must exist, or --dir fails closed
        for rel in (LOOKALIKE_SIBLING, LOOKALIKE_WORD):
            with self.subTest(rel=rel):
                self.put(rel + "/" + LONG)
                self.assert_passes("--dir", DOCS, rel + "/" + LONG)

    def test_named_decisions_folder_matches_the_default(self):
        self.put("decisions/" + LONG)
        rc, out = self.lint("--dir", "decisions", "decisions/" + LONG)
        self.assertEqual(rc, 1, out)
        self.assertEqual(flagged(out), ["decisions/" + LONG])

    def test_default_diff_flags_only_the_default_folders(self):
        self.commit_base()
        self.put("decisions/" + LONG)
        self.put(DOCS + "/" + LONG)
        self.commit_change()
        rc, out = self.lint()  # no file arguments: the diff against origin/main
        self.assertEqual(rc, 1, out)
        self.assertEqual(flagged(out), ["decisions/" + LONG])

    def test_dir_diff_flags_only_the_named_folder(self):
        self.commit_base()
        self.put("decisions/" + LONG)
        self.put(DOCS + "/" + LONG)
        self.commit_change()
        rc, out = self.lint("--dir", DOCS)
        self.assertEqual(rc, 1, out)
        self.assertEqual(flagged(out), [DOCS + "/" + LONG])

    # --dir must name a folder that exists under the checkout, spelled as it is on disk. A check
    # that cannot read its own input exits non-zero, and names the folder it was given.
    # Case: on a case-insensitive disk "Decisions" resolves, so the spelling must be compared too.

    def test_dir_that_names_no_usable_folder_fails(self):
        self.put("decisions/" + OK)
        self.put("README.md")
        for value in ("decision", "docs/decisions-old", ".", "", "Decisions",
                      "README.md", "decisions/" + OK):
            with self.subTest(dir=value):
                rc, out = self.lint("--dir", value, "decisions/" + OK)
                self.assertNotEqual(rc, 0, out)
                self.assertIn("'%s'" % value, out)
                self.assertNotIn("Traceback", out)

    def test_dir_without_a_value_fails(self):
        self.put("decisions/" + OK)
        rc, out = self.lint("decisions/" + OK, "--dir")  # --dir is last: no folder is given
        self.assertNotEqual(rc, 0, out)
        self.assertIn("''", out)
        self.assertNotIn("Traceback", out)

    def test_dir_that_names_no_usable_folder_fails_in_the_diff(self):
        self.commit_base()
        self.put("decisions/" + OK)
        self.commit_change()
        rc, out = self.lint("--dir", "decision")
        self.assertNotEqual(rc, 0, out)
        self.assertIn("'decision'", out)
        self.assertNotIn("Traceback", out)


    def test_backslash_path_is_checked_like_a_slash_path(self):
        # A Windows-style path names the same record, so its folder must still be read.
        self.assert_passes("decisions\\" + OK)
        rc, out = self.lint("decisions\\" + LONG)
        self.assertEqual(rc, 1, out)
        self.assertEqual(flagged(out), ["decisions\\" + LONG])

    def test_dir_given_twice_fails(self):
        self.put("decisions/" + OK)
        rc, out = self.lint("--dir", "decisions", "--dir", "bogus", "decisions/" + OK)
        self.assertNotEqual(rc, 0, out)
        self.assertIn("given more than once", out)
        self.assertNotIn("Traceback", out)


if __name__ == "__main__":
    unittest.main()
