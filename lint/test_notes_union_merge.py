#!/usr/bin/env python3
"""Fixture suite for the merge of docs/debts/notes.md, the file every lane appends one line to.

Each case builds a throwaway git repo that holds this checkout's real .gitattributes and a small notes.md,
branches lanes off one base, and merges them into main with `git merge --no-ff`. Without `merge=union` on
that file, two lanes that each append a line clash on the last line of the file.

Red cases: two lanes that each append a line; three lanes merged forward and in reverse; two lanes that
rewrite one note; the real checkout with no `merge=union` on notes.md. The generated docs/records.md and
docs/catalog.md must stay off union: the merge tool rebuilds them, so a union of two copies hides a bad merge.
Run: python3 lint/test_notes_union_merge.py
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (the one home, lint/_test_temp.py)

ROOT = os.path.dirname(HERE)
ATTRIBUTES = os.path.join(ROOT, ".gitattributes")
NOTES = "docs/debts/notes.md"
RUN_FOLDER = _test_temp.run_folder()

# Same git isolation as lint/test_tracked_tree.py: no user or system config, a fixed author.
ENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull, GIT_AUTHOR_NAME="t",
           GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")

HEADING = "# Notes: findings too unlikely to hit to be debts"
OLD = "- shared-note: the old wording of one note (hooks/guard.py)"
BASE_LINES = [HEADING, "- first-note: a finding from an earlier batch (lint/check_a.py)", OLD,
              "- last-note: the last line of the base file (merge/merge.py)"]
MARKERS = ("<<<<<<<", "=======", ">>>>>>>")


def git(root, *args):
    return subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, env=ENV)


def git_ok(root, *args):
    done = git(root, *args)
    if done.returncode != 0:
        raise AssertionError("git %s failed (%d): %s%s" % (" ".join(args), done.returncode, done.stdout, done.stderr))
    return done


def attr_merge(root, path):
    """The value `git check-attr` reports for the merge attribute of `path`: `union`, `unspecified`, ..."""
    done = git_ok(root, "check-attr", "merge", "--", path)
    return done.stdout.strip().rsplit(": ", 1)[-1]


class NotesRepo(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="notes_", dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, self.root, True)
        git_ok(self.root, "init", "-q", "-b", "main")
        shutil.copyfile(ATTRIBUTES, os.path.join(self.root, ".gitattributes"))  # the branch's real file, never a fixture line
        self.write("\n".join(BASE_LINES) + "\n")
        git_ok(self.root, "add", "-A")
        git_ok(self.root, "commit", "-q", "-m", "base")
        self.base = git_ok(self.root, "rev-parse", "HEAD").stdout.strip()

    def path(self):
        return os.path.join(self.root, *NOTES.split("/"))

    def write(self, text):
        os.makedirs(os.path.dirname(self.path()), exist_ok=True)
        with open(self.path(), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

    def read(self):
        with open(self.path(), encoding="utf-8", newline="") as f:
            return f.read()

    def lane(self, name, edit):
        """A branch off the base commit whose notes.md is `edit(base text)`. Main is checked out again after."""
        git_ok(self.root, "checkout", "-q", "-b", name, self.base)
        self.write(edit(self.read()))
        git_ok(self.root, "commit", "-q", "-am", name)
        git_ok(self.root, "checkout", "-q", "main")

    def append_lane(self, name, line):
        self.lane(name, lambda text: text + line + "\n")
        return line

    def merge(self, name):
        return git(self.root, "merge", "--no-ff", "--no-edit", name)

    def assert_merged(self, done, name):
        """The merge exited 0 and left no unmerged path and no conflict marker in the file."""
        self.assertEqual(done.returncode, 0, "merge of %s: %s%s" % (name, done.stdout, done.stderr))
        self.assertEqual(git_ok(self.root, "diff", "--name-only", "--diff-filter=U").stdout.strip(), "")
        for line in self.read().splitlines():
            self.assertFalse(line.startswith(MARKERS), "conflict marker left in %s: %r" % (NOTES, line))

    def assert_lines_once(self, lines, wanted):
        for line in wanted:
            self.assertEqual(lines.count(line), 1, "%r appears %d times in:\n%s" % (line, lines.count(line), "\n".join(lines)))


class AppendedLines(NotesRepo):
    def test_two_lanes_that_each_append_a_line_merge_clean(self):
        one = self.append_lane("lane-one", "- one-note: appended by the first lane (lint/check_one.py)")
        two = self.append_lane("lane-two", "- two-note: appended by the second lane (lint/check_two.py)")
        self.assert_merged(self.merge("lane-one"), "lane-one")
        self.assert_merged(self.merge("lane-two"), "lane-two")
        lines = self.read().splitlines()
        self.assertEqual(lines[0], HEADING)
        self.assert_lines_once(lines, BASE_LINES + [one, two])
        self.assertEqual(len(lines), len(BASE_LINES) + 2)
        self.assertTrue(self.read().endswith("\n"))
        self.assertEqual(len(git_ok(self.root, "rev-list", "--parents", "-n", "1", "HEAD").stdout.split()), 3,
                         "the last merge is not a two-parent merge commit")

    def merge_three(self, order):
        added = {n: self.append_lane("lane-" + n, "- %s-note: appended by lane %s (lint/check_%s.py)" % (n, n, n))
                 for n in ("a", "b", "c")}
        for n in order:
            self.assert_merged(self.merge("lane-" + n), "lane-" + n)
        lines = self.read().splitlines()
        self.assertEqual(lines[0], HEADING)
        self.assertEqual(lines[:len(BASE_LINES)], BASE_LINES)
        self.assert_lines_once(lines, BASE_LINES + list(added.values()))
        self.assertEqual(len(lines), len(BASE_LINES) + 3)

    def test_three_lanes_merge_clean_in_order(self):
        self.merge_three(("a", "b", "c"))

    def test_three_lanes_merge_clean_in_reverse_order(self):
        self.merge_three(("c", "b", "a"))


class RewrittenNote(NotesRepo):
    def test_two_rewrites_of_one_note_keep_both_versions(self):
        """Pins the failure mode of `merge=union`: it never stops on a clash, so two lanes that rewrite the same
        note both stay in the file and the old line goes. The reader merges the two by hand later. This is the
        accepted cost: a merge that stops on every appended line is worse, since lanes append all the time."""
        one = "- shared-note: the first lane's wording of one note (hooks/guard.py)"
        two = "- shared-note: the second lane's wording of one note (hooks/guard.py)"
        self.lane("lane-one", lambda text: text.replace(OLD, one))
        self.lane("lane-two", lambda text: text.replace(OLD, two))
        self.assert_merged(self.merge("lane-one"), "lane-one")
        self.assert_merged(self.merge("lane-two"), "lane-two")
        lines = self.read().splitlines()
        self.assertNotIn(OLD, lines)
        self.assert_lines_once(lines, [one, two])
        self.assertEqual(lines[0], HEADING)


class RealCheckout(unittest.TestCase):
    def test_notes_use_the_union_driver(self):
        self.assertEqual(attr_merge(ROOT, NOTES), "union", "add `%s merge=union` to .gitattributes" % NOTES)

    def test_generated_pages_stay_off_union(self):
        for page in ("docs/records.md", "docs/catalog.md"):
            self.assertTrue(os.path.isfile(os.path.join(ROOT, *page.split("/"))), "%s moved: repoint this case" % page)
            self.assertNotEqual(attr_merge(ROOT, page), "union", "%s is regenerated by the merge tool" % page)


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


if __name__ == "__main__":
    unittest.main()
