#!/usr/bin/env python3
"""Cases for lint/check_debt_decision.py. Standard library only.

    python3 lint/test_check_debt_decision.py

A debt links its decision. A debt is a file in docs/debts/, not a folder's README.md or notes.md.
Its Decision part is the line `**Decision.**` at column one or after `- ` (docs/debts/README.md).
The value names the decision by its slug, or is `none`.

The check reads the lines the change adds or edits (origin/main...HEAD) in docs/debts/. It judges each Decision line:

- the first word of the value, with backticks, quote marks and trailing punctuation dropped, is `none`, or the
  slug of a decision file in docs/decisions/ of the tree;
- a first word with a `/` (a path cite), or ending `.md`, is red, whatever it names;
- a debt the change adds with no Decision part is red.

Each FAIL line, `check_debt_decision: FAIL: ...`, names one cause. A debt with no Decision part has no line
to name, so its FAIL line names the path alone.

Each case builds a temp git repo. origin/main is the base, HEAD the change. The module runs from that tree.
DEBT_DECISION_UNDER_TEST overrides the module path, for a mutant copy.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per test run (lint/_test_temp.py)
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import tracked_tree  # noqa: E402  copies what git lists, so no fixture lists files (testing/tracked_tree.py)

MODULE = os.environ.get("DEBT_DECISION_UNDER_TEST") or os.path.join(HERE, "check_debt_decision.py")
DECISION = "docs/decisions/merge-lock.md"  # the decision the cases link: its slug is merge-lock
DECISION_NEW = "docs/decisions/lock-expires.md"  # a decision the same change adds
DEBT = "docs/debts/lock-read-error.md"  # the debt the cases add or edit
NOTES = "docs/debts/notes.md"  # the folder's notes file: not a debt
ROOT_FILE = "scratch-note.txt"  # a file outside the debts folder: a change that adds no debt line
MERGE_LOCK = "# Merge lock\n\nOne lock per base, so two runs cannot race.\n"
WHAT = "- **What.** A read error leaves the lock held.\n"
WHERE = "- **Where.** merge/merge.py, the lock read.\n"
RETIRE = "- **Retire.** `test_lock_read.py` shows the lock expires.\n"
DECISION_LINE = 5  # debt() puts the Decision part on file line 5

RUN_FOLDER = None  # made in setUpModule, so an import leaks no folder


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


def debt(decision, what=WHAT):
    """A debt with its four parts. The Decision part is file line 5, as DECISION_LINE says."""
    return "# Lock read error\n\n" + what + WHERE + "- **Decision.** " + decision + "\n" + RETIRE


def flagged(out):
    """The FAIL lines the check printed."""
    return [line for line in out.splitlines() if line.startswith("check_debt_decision: FAIL:")]


class DebtDecisionTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(os.path.isfile(MODULE), "module absent: lint/check_debt_decision.py")
        self.tree = tempfile.mkdtemp(prefix="cdd_", dir=RUN_FOLDER)
        self.addCleanup(tracked_tree.rm_tree, self.tree)
        tracked_tree.copy_tracked(self.tree, "lint", "hooks")  # the layout and the check's imports
        shutil.copyfile(MODULE, os.path.join(self.tree, "lint", "check_debt_decision.py"))
        self.git("init", "-q")
        self.base({DECISION: MERGE_LOCK})  # merge-lock is a decision from the start

    def git(self, *args):
        subprocess.run(["git", "-C", self.tree, "-c", "user.name=test", "-c", "user.email=test@example.com", *args],
                       check=True, capture_output=True, text=True)

    def put(self, rel, text):
        path = os.path.join(self.tree, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

    def base(self, files):
        """Commit `files` and point origin/main at the commit: the base the check diffs against."""
        for rel, text in files.items():
            self.put(rel, text)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "base")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")

    def change(self, files):
        """Commit `files` on top of origin/main. The diff must name each path first (scope before subject)."""
        for rel, text in files.items():
            self.put(rel, text)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "change")
        named = subprocess.run(["git", "-C", self.tree, "diff", "--name-only", "origin/main...HEAD"],
                               check=True, capture_output=True, text=True).stdout.split()
        for rel in files:
            self.assertIn(rel, named, "the change does not name %s" % rel)

    def lint(self):
        env = dict(os.environ)
        env.pop("CI", None)  # CI makes an unknown read red; these cases run locally
        cmd = [sys.executable, os.path.join(self.tree, "lint", "check_debt_decision.py")]
        r = subprocess.run(cmd, cwd=self.tree, env=env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        return r.returncode, r.stdout + r.stderr

    def assert_passes(self):
        rc, out = self.lint()
        self.assertEqual(rc, 0, out)
        self.assertEqual(flagged(out), [], out)

    def assert_flags(self, *cases):
        """Red: exit 1, with one FAIL line for each (path, line, text) given and no other.

        A line of 0 marks a debt with no Decision part. Its FAIL line names the path alone."""
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        lines = flagged(out)
        self.assertEqual(len(lines), len(cases), out)
        for path, line, text in cases:
            where = "%s:%d: " % (path, line) if line else "%s: " % path
            hits = [got for got in lines if where in got and text in got]
            self.assertEqual(len(hits), 1, "no FAIL line for %s naming %s\n%s" % (where, text, out))

    # Positive controls first: a red case means nothing if the clean case fails.

    def test_default_passes_a_debt_that_links_a_decision_by_slug(self):
        self.change({DEBT: debt("`merge-lock` (one lock per base).")})
        self.assert_passes()

    def test_default_passes_a_bare_decision_slug_without_a_dash(self):
        self.change({DEBT: "# Lock read error\n\n" + WHAT + WHERE + "**Decision.** merge-lock, one lock per base.\n"
                           + RETIRE})
        self.assert_passes()

    def test_default_passes_none(self):
        self.change({DEBT: debt("`none`.")})
        self.assert_passes()

    def test_default_passes_none_with_a_note_after_it(self):
        self.change({DEBT: debt("none on main, a draft is pending.")})
        self.assert_passes()

    def test_default_passes_a_decision_the_same_change_adds(self):
        self.change({
            DECISION_NEW: "# Lock expires\n\nA lock expires after its read.\n",
            DEBT: debt("`lock-expires` (a lock expires after its read)."),
        })
        self.assert_passes()

    def test_default_passes_a_quoted_decision_inside_a_code_span(self):
        self.change({DEBT: debt('`"merge-lock"` (one lock per base).')})
        self.assert_passes()

    def test_default_passes_an_empty_change(self):
        # Empty state: the change adds no debt line, so nothing is judged.
        self.change({ROOT_FILE: "nothing in the debts folder\n"})
        self.assert_passes()

    # Red: each case names the one Decision part it must flag.

    def test_default_flags_a_decision_slug_that_names_no_file(self):
        self.change({DEBT: debt("`merge-lok` (typo).")})
        self.assert_flags((DEBT, DECISION_LINE, "merge-lok"))

    def test_default_flags_a_decision_cited_by_path(self):
        self.change({DEBT: debt("`docs/decisions/merge-lock.md` (one lock per base).")})
        self.assert_flags((DEBT, DECISION_LINE, "path"))

    def test_default_flags_a_quoted_decision_inside_a_code_span_that_names_no_file(self):
        self.change({DEBT: debt('`"merge-lok"` (one lock per base).')})
        self.assert_flags((DEBT, DECISION_LINE, "merge-lok"))

    def test_default_flags_a_new_debt_with_no_decision_part(self):
        self.change({DEBT: "# Lock read error\n\n" + WHAT + WHERE + RETIRE})
        self.assert_flags((DEBT, 0, "Decision part"))

    def test_default_flags_a_changed_decision_line_on_an_existing_debt(self):
        self.base({DEBT: debt("`none`.")})
        self.change({DEBT: debt("`merge-lok` (typo).")})
        self.assert_flags((DEBT, DECISION_LINE, "merge-lok"))

    # Scope: only a Decision line the change adds or edits is judged.

    def test_default_ignores_a_bad_decision_line_on_an_unchanged_line(self):
        self.base({DEBT: debt("`merge-lok` (typo).")})
        self.change({DEBT: debt("`merge-lok` (typo).", what="- **What.** A read error holds the lock.\n")})
        self.assert_passes()

    def test_default_leaves_the_debt_notes_file_unchecked(self):
        self.change({NOTES: "# Notes\n\n- **Decision.** `merge-lok` (typo).\n"})
        self.assert_passes()


if __name__ == "__main__":
    unittest.main()
