#!/usr/bin/env python3
"""Cases for lint/check_cite_gloss.py. Standard library only.

    python3 lint/test_check_cite_gloss.py

A record glosses each record id it cites on the id's first use in that record.
A record is a file in docs/decisions/ or docs/debts/, not a folder's README.md or docs/debts/notes.md.
A record id is the slug of such a file.
The gloss is the text right after the cite's closing backtick: ` (` then a word, or `,` then a word.
That is the form stamp's glossFirstUse reads (actions/stamp/formats/heading.mjs). A colon is no gloss.

The check reads the lines the change adds or edits (origin/main...HEAD). It judges only a first use on one of them:

- a cite is a backticked span whose content, with quote marks and spaces dropped, is a record id;
- the first use of an id is its first cite in the file, counted from the top, on a line that is not a heading;
- a cite of the record's own slug needs no gloss: the record names itself;
- a first use with no gloss is red. Its FAIL line, `check_cite_gloss: FAIL: ...`, names the path, the line, the slug.

A run that cannot read its base prints UNKNOWN. Locally that exits 0; under CI it exits 1 (decision ci-unknown-is-red).
assert_passes fails a run that printed UNKNOWN, so no case passes on an unread base.

Each case builds a temp git repo. origin/main is the base, HEAD the change. The module runs from that tree.
CITE_GLOSS_UNDER_TEST overrides the module path, for a mutant copy. RECORD_DIFF_UNDER_TEST overrides the shared
helper lint/_record_diff.py the same way, so the UNKNOWN branch can be silenced in a mutant.
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

MODULE = os.environ.get("CITE_GLOSS_UNDER_TEST") or os.path.join(HERE, "check_cite_gloss.py")
RECORD_DIFF = os.environ.get("RECORD_DIFF_UNDER_TEST")  # a mutant of lint/_record_diff.py, else the tree's own copy
DECISION = "docs/decisions/merge-lock.md"  # the record the cases cite: its slug is merge-lock
LOCK_HELD = "docs/decisions/lock-held.md"  # a decision that cites its own slug: its slug is lock-held
DEBT = "docs/debts/lock-read-error.md"  # the debt the cases add or edit
NOTES = "docs/debts/notes.md"  # the folder's notes file: a list of notes, not a record
PLAN = "docs/plans/lock-plan.md"  # a plan: a record in the glossary, but not in this check's folders
ROOT_FILE = "scratch-note.txt"  # a file outside every record folder: a change that adds no record line
MERGE_LOCK = "# Merge lock\n\nOne lock per base, so two runs cannot race.\n"

RUN_FOLDER = None  # made in setUpModule, so an import leaks no folder


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


def record(*lines):
    """A debt with a title and a blank line, then one body line each. Body line i is file line i + 3."""
    return "# Lock read error\n\n" + "".join(line + "\n" for line in lines)


def flagged(out):
    """The FAIL lines the check printed."""
    return [line for line in out.splitlines() if line.startswith("check_cite_gloss: FAIL:")]


class CiteGlossTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(os.path.isfile(MODULE), "module absent: lint/check_cite_gloss.py")
        self.tree = tempfile.mkdtemp(prefix="cgl_", dir=RUN_FOLDER)
        self.addCleanup(tracked_tree.rm_tree, self.tree)
        tracked_tree.copy_tracked(self.tree, "lint", "hooks")  # the layout and the check's imports
        if RECORD_DIFF:
            shutil.copyfile(RECORD_DIFF, os.path.join(self.tree, "lint", "_record_diff.py"))
        shutil.copyfile(MODULE, os.path.join(self.tree, "lint", "check_cite_gloss.py"))
        self.git("init", "-q")
        self.base({DECISION: MERGE_LOCK})  # merge-lock is a record id from the start

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

    def lint(self, base=None, ci=False):
        """Run the check. `base` names the ref to diff against (default origin/main). `ci` sets CI, as the workflow does."""
        env = dict(os.environ)
        env.pop("CI", None)  # CI makes an unknown read red; the default run is local
        if ci:
            env["CI"] = "true"
        cmd = [sys.executable, os.path.join(self.tree, "lint", "check_cite_gloss.py")]
        if base:
            cmd += ["--base", base]
        r = subprocess.run(cmd, cwd=self.tree, env=env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        return r.returncode, r.stdout + r.stderr

    def unreadable_base(self):
        """A ref the tree does not hold. Scope before subject: the case reads UNKNOWN only if this ref is absent."""
        probe = subprocess.run(["git", "-C", self.tree, "rev-parse", "--verify", "--quiet", "no-such-ref"],
                               capture_output=True, text=True)
        self.assertNotEqual(probe.returncode, 0, "no-such-ref must be absent for this case")
        return "no-such-ref"

    def assert_passes(self, base=None):
        rc, out = self.lint(base=base)
        self.assertEqual(rc, 0, out)
        self.assertNotIn("UNKNOWN", out, "a run that printed UNKNOWN is not a pass\n" + out)
        self.assertEqual(flagged(out), [], out)

    def assert_flags(self, *cases):
        """Red: exit 1, and one FAIL line for each (path, line, slug) given, with no other FAIL line."""
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        lines = flagged(out)
        self.assertEqual(len(lines), len(cases), out)
        for path, line, slug in cases:
            hits = [got for got in lines if "%s:%d: " % (path, line) in got and slug in got]
            self.assertEqual(len(hits), 1, "no FAIL line for %s:%d naming %s\n%s" % (path, line, slug, out))

    # Positive controls first: a red case means nothing if the clean case fails.

    def test_default_passes_a_first_cite_with_a_comma_gloss(self):
        self.change({DEBT: record("The lock is `merge-lock`, one lock per base, so runs cannot race.")})
        self.assert_passes()

    def test_default_passes_a_first_cite_with_a_paren_gloss(self):
        self.change({DEBT: record("The lock is `merge-lock` (one lock per base) for each base.")})
        self.assert_passes()

    def test_default_passes_a_quoted_id_inside_a_code_span_with_a_gloss(self):
        self.change({DEBT: record('The flag takes `"merge-lock"` (one lock per base) as its value.')})
        self.assert_passes()

    def test_default_passes_the_second_use_after_a_glossed_first_use(self):
        self.change({DEBT: record("The lock is `merge-lock`, one lock per base.", "Runs wait on `merge-lock`.")})
        self.assert_passes()

    def test_default_passes_an_empty_change(self):
        # Empty state: the change adds no record line, so nothing is judged.
        self.change({ROOT_FILE: "nothing in a record folder\n"})
        self.assert_passes()

    def test_default_ignores_a_bare_cite_inside_a_real_fence(self):
        # A fenced block holds no use: the bare cite inside it is not a first use, and the glossed one after it passes.
        self.change({DEBT: record("```", "The lock is `merge-lock`.", "```", "Runs wait on `merge-lock`, one lock per base.")})
        self.assert_passes()

    def test_default_passes_a_glossed_cite_in_a_table_cell(self):
        self.change({DEBT: record("| Id | Meaning |", "|---|---|", "| `merge-lock` (one lock per base) | the lock |")})
        self.assert_passes()

    # Red: each case names the one first use it must flag.

    def test_default_flags_a_bare_first_cite(self):
        self.change({DEBT: record("The lock is `merge-lock`.")})
        self.assert_flags((DEBT, 3, "merge-lock"))

    def test_default_flags_a_quoted_id_inside_a_code_span(self):
        self.change({DEBT: record('The flag takes `"merge-lock"` as its value.')})
        self.assert_flags((DEBT, 3, "merge-lock"))

    def test_default_flags_a_bare_cite_after_a_lone_quote(self):
        # A lone double quote in prose must not hide the cite that follows it.
        self.change({DEBT: record('He said "the lock is `merge-lock`.')})
        self.assert_flags((DEBT, 3, "merge-lock"))

    def test_default_flags_a_colon_after_the_cite(self):
        # A colon is no gloss: the form is ` (` or `, word`.
        self.change({DEBT: record("The lock is `merge-lock`: one lock per base.")})
        self.assert_flags((DEBT, 3, "merge-lock"))

    def test_default_flags_only_the_first_use_of_an_id(self):
        self.change({DEBT: record("The lock is `merge-lock`.", "Runs wait on `merge-lock`.")})
        self.assert_flags((DEBT, 3, "merge-lock"))

    def test_default_flags_a_bare_cite_an_edit_adds(self):
        self.base({DEBT: record("The lock is held.")})
        self.change({DEBT: record("The lock is `merge-lock`.")})
        self.assert_flags((DEBT, 3, "merge-lock"))

    def test_default_flags_a_bare_first_cite_in_a_new_decision(self):
        lock_held = "docs/decisions/lock-held.md"
        self.change({lock_held: "# Lock held\n\nA held lock blocks `merge-lock`.\n"})
        self.assert_flags((lock_held, 3, "merge-lock"))

    def test_full_size_debt_flags_a_bare_cite_at_its_line(self):
        # Full size: 253 lines. The one bare first use is file line 203; a later bare use is a second use and passes.
        body = ["Prose line %d about the read path." % i for i in range(200)]
        body += ["The lock is `merge-lock`."]
        body += ["Prose line %d about the read path." % i for i in range(200, 249)]
        body += ["Runs wait on `merge-lock`."]
        self.change({DEBT: record(*body)})
        self.assert_flags((DEBT, 203, "merge-lock"))

    def test_default_flags_a_bare_cite_after_a_line_that_opens_with_a_code_span(self):
        # "```x```" is a code span, not a fence: it must not open a block that hides the rest of the record.
        self.change({DEBT: record("```x``` is a code span, not a fence.", "The lock is `merge-lock`.")})
        self.assert_flags((DEBT, 4, "merge-lock"))

    def test_default_flags_a_bare_cite_in_a_table_cell(self):
        self.change({DEBT: record("| Id | Meaning |", "|---|---|", "| `merge-lock` | the lock |")})
        self.assert_flags((DEBT, 5, "merge-lock"))

    def test_default_passes_a_record_that_cites_its_own_slug_without_a_gloss(self):
        # The record names itself: its own slug is no first use that needs a gloss.
        self.change({LOCK_HELD: "# Lock held\n\nA held lock blocks the merge (rule `lock-held`).\n"})
        self.assert_passes()

    def test_default_flags_another_id_a_record_cites_beside_its_own_slug(self):
        # Only the record's own slug is exempt: the other bare first cite on the same line is still red.
        self.change({LOCK_HELD: "# Lock held\n\nA held lock is `lock-held` and blocks `merge-lock`.\n"})
        self.assert_flags((LOCK_HELD, 3, "merge-lock"))

    # Scope: only a record's first use on a changed line is judged.

    def test_default_ignores_a_bare_cite_already_on_an_unchanged_line(self):
        self.base({DEBT: record("The lock is `merge-lock`.")})
        self.change({DEBT: record("The lock is `merge-lock`.", "Runs wait on `merge-lock`.")})
        self.assert_passes()

    def test_default_ignores_a_heading_cite(self):
        # A heading is no use: the first use is the body cite, which is glossed.
        self.change({DEBT: "# The `merge-lock` read error\n\nThe lock is `merge-lock`, one lock per base.\n"})
        self.assert_passes()

    def test_default_ignores_a_backticked_name_that_is_no_record(self):
        self.change({DEBT: record("`GhLock` reads the lock file.")})
        self.assert_passes()

    def test_default_leaves_plans_unchecked(self):
        self.change({PLAN: "# Lock plan\n\nThe lock is `merge-lock`.\n"})
        self.assert_passes()

    def test_default_leaves_the_debt_notes_file_unchecked(self):
        self.change({NOTES: "# Notes\n\n- lock-read-error: `merge-lock` races on a read error.\n"})
        self.assert_passes()

    # An unread base is UNKNOWN: exit 0 locally, exit 1 under CI (decision ci-unknown-is-red).
    # Each case has a bare first use, so a run that read the change would print a FAIL line.

    def test_default_gives_unknown_on_an_unreadable_base(self):
        self.change({DEBT: record("The lock is `merge-lock`.")})
        rc, out = self.lint(base=self.unreadable_base())
        self.assertIn("check_cite_gloss: UNKNOWN", out, out)
        self.assertEqual(rc, 0, out)

    def test_ci_fails_an_unreadable_base(self):
        self.change({DEBT: record("The lock is `merge-lock`.")})
        rc, out = self.lint(base=self.unreadable_base(), ci=True)
        self.assertIn("check_cite_gloss: UNKNOWN", out, out)
        self.assertEqual(rc, 1, out)

    def test_assert_passes_fails_a_run_that_printed_unknown(self):
        self.change({DEBT: record("The lock is `merge-lock`, one lock per base.")})
        with self.assertRaises(AssertionError) as caught:
            self.assert_passes(base=self.unreadable_base())
        self.assertIn("UNKNOWN", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
