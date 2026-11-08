#!/usr/bin/env python3
"""Cases for lint/check_record_slugs.py. Standard library only.

    python3 lint/test_check_record_slugs.py

A record file that a change adds must have a slug of 32 characters or fewer. The check reads
decisions/ and debts/ from the diff, or the files it is given.

Each case builds a temp tree: a copy of the module, and the records it checks. It runs the real
script from that tree. The diff cases also make a temp git repo and set refs/remotes/origin/main,
the base the script diffs against. RECORD_SLUGS_UNDER_TEST overrides the module path.
"""
import contextlib
import importlib.util
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
MODULE = os.environ.get("RECORD_SLUGS_UNDER_TEST") or os.path.join(HERE, "check_record_slugs.py")
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import tracked_tree  # noqa: E402  copies what git lists, so no fixture lists files (testing/tracked_tree.py)

OK = "a" * 32 + ".md"  # a slug of 32 characters passes
LONG = "a" * 33 + ".md"  # a slug of 33 characters fails
VERY_LONG = "a" * 44 + ".md"  # a slug of 44 characters fails, for the ./ path case
DOCS = "docs/decisions"  # a folder the default run does not read
FEEL_DEBT = "debts/scroll-jank.md"  # a feel-fix debt with no device check
CHECKED_DEBT = "debts/tap-lag.md"  # a feel-fix debt with a device check
PLAIN_DEBT = "debts/stale-link.md"  # a debt that is not a feel-fix
# A lone quote in the text is one of the traps a line scanner must pass.
FEEL_TEXT = "# Scroll jank\n\nDon't scroll the list while it loads.\n\n**Feel.** Motion is off on touch.\n"
CHECKED_TEXT = ("# Tap lag\n\nTaps land late on the first screen.\n\n**Feel.** Touch timing is off.\n\n"
                "**Device check.** simulator, 2026-11-01T11:44:00-06:00\n")
PLAIN_TEXT = "# Stale link\n\nA plain debt.\n"
BULLET_DEBT = "debts/bullet-jank.md"  # a bullet-form feel-fix with no device check
BULLET_CHECKED = "debts/bullet-tap.md"  # a bullet-form feel-fix with a device check
MID_LINE = "debts/mid-line.md"  # a Feel marker that is not at a line start
DEBT_README = "debts/README.md"  # the folder's README: it describes the markers, it is not a debt
DEBT_NOTES = "debts/notes.md"  # the folder's notes file: it is not a debt either
README_FEEL_TEXT = "# Debts\n\nOne debt per file.\n\n- **Feel.** a marker shown as an example, not a debt\n"
NOTES_FEEL_TEXT = "# Notes\n\n- **Feel.** a note that is not a debt\n"
FIXED_DEBT_TEXT = "# Long slug\n\nWhat. A gap with a fix named.\n\nFix: none — owner decides\n"  # a valid Fix line
# The Fix field of a notes line and of a debt file. origin/roadmap holds the step alpha-beta, never alpha.
STEP_JSON = '{"id": "alpha-beta"}\n'  # a roadmap step file: the check reads only that it exists
ALPHA_STEP = "roadmap/data/steps/alpha.json"  # a step file on HEAD only, not on origin/roadmap
NOTES_HEAD = "# Notes: findings too unlikely to hit to be debts\n"
OLD_NOTE = "- old-note: an old gap. Fix: pin the base.\n"  # a line the base holds before the branch
NEW_NO_FIX = "- new-note: a gap nobody named.\n"
NEW_PROSE_FIX = "- new-note: a gap. Fix: pin the base.\n"
NEW_ABSENT_STEP = "- new-note: a gap. Fix: step:alpha\n"
NEW_BAD_REASON = "- new-note: a gap. Fix: none — someday. Until: 2026-11-20\n"
NEW_VALID_STEP = "- new-note: a gap. Fix: step:alpha-beta\n"
NEW_VALID_NONE = "- new-note: a gap. Fix: none — owner decides. Until: 2026-11-20\n"
VALID_LINES = (  # every form that passes: a step, both dashes, and each reason on the list
    "- step-note: a gap. Fix: step:alpha-beta\n",
    "- owner-note: a gap. Fix: none — owner decides. Until: 2026-11-20\n",
    "- mac-note: a gap. Fix: none -- needs the Mac. Until: 2026-11-20\n",
    "- rare-note: a gap. Fix: none — rare and harmless. Until: 2026-11-20\n",
)
NEW_DEBT = "debts/new-debt.md"  # a new debt file with no Fix line
FIXED_DEBT = "debts/fixed-debt.md"  # a new debt file with a valid Fix line, beside NEW_DEBT in the same diff
DEBT_NO_FIX = "# New debt\n\nWhat. A gap with no fix named.\n"
PINNED_TODAY = "2026-11-07"  # the date the suite pins: the check reads FIXED_TODAY, so no case reads the clock
KEPT_NOTE = "- kept-note: a gap. Fix: already fixed on main 1a2b3c4\n"  # a bullet with a new-grammar Fix
THIRD_NOTE = "- third-note: a gap. Fix: already fixed on main 1a2b3c4\n"
COST_NOTE = ("- cost-note: a gap. Fix: none — rare and harmless: 8,000 characters take 1.3 s. "
             "Until: 2026-11-20\n")  # a none reason, then a cost, and no check output
COMMIT_NOTE = ("- commit-note: a gap. Fix: none — owner decides: the open lane y (a52e7a0fe) makes it linear. "
               "Until: 2026-11-20\n")  # a none reason, then a commit and a complexity word
SCOPE_NOTE = "- scope-note: a gap. Fix: none — owner decides\n"  # no Until: the Until rule refuses it today
CHECK = "`verdict python3 x.py`"  # check output: a backticked command, then its verdict word
SIX = "a52e7a"  # 6 hex characters: too short to name a commit
SEVEN = "a52e7a0"  # 7: the shortest hex token that names a commit
FORTY = "a52e7a0fe" * 4 + "a52e"  # 40: the longest hex token that names a commit
FORTY_ONE = FORTY + "7"  # 41: too long to name a commit

RUN_FOLDER = None  # made in setUpModule, so an import leaks no folder


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


def fail_lines(out):
    """Each FAIL line the check printed, whole."""
    return [line for line in out.splitlines() if line.startswith("check_record_slugs: FAIL:")]


def flagged(out):
    """The paths the check named as FAIL: each FAIL line ends with its path."""
    return [line.rsplit(" ", 1)[1] for line in fail_lines(out)]


def none_note(slug, text):
    """A notes line whose Fix is none, with `text` after the reason, dated inside the Until cap."""
    return "- %s: a gap. Fix: none — %s. Until: 2026-11-20\n" % (slug, text)


class RecordSlugsTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(os.path.isfile(MODULE), "module absent: lint/check_record_slugs.py")
        self.tree = tempfile.mkdtemp(prefix="rsl_", dir=RUN_FOLDER)
        self.addCleanup(tracked_tree.rm_tree, self.tree)
        tracked_tree.copy_tracked(self.tree, "lint", "hooks")  # the layout and the check's imports
        shutil.copyfile(MODULE, os.path.join(self.tree, "lint", "check_record_slugs.py"))

    def put(self, rel, text="# Record\n"):
        path = os.path.join(self.tree, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

    def lint(self, *args):
        env = dict(os.environ)
        env.pop("CI", None)  # CI turns an unknown diff into red; these cases run locally
        env["FIXED_TODAY"] = PINNED_TODAY  # the check's date comes from here, never from the clock
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
                        "-c", "user.email=test@example.com", *args],
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

    def delete(self, *rels):
        for rel in rels:
            os.remove(os.path.join(self.tree, *rel.split("/")))

    def move(self, old, new):
        dest = os.path.join(self.tree, *new.split("/"))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        os.rename(os.path.join(self.tree, *old.split("/")), dest)

    def loose_blob(self, ref_path):
        """The loose object file of the blob at `ref_path` on origin/main. Removing it makes git show fail."""
        sha = subprocess.run(["git", "-C", self.tree, "rev-parse", "origin/main:" + ref_path],
                             capture_output=True, text=True, check=True).stdout.strip()
        return os.path.join(self.tree, ".git", "objects", sha[:2], sha[2:])

    def roadmap(self, *slugs):
        """Point refs/remotes/origin/roadmap at a commit that holds one step file for each slug. The commit is built
        in a temp index, so HEAD and the working tree do not move."""
        env = dict(os.environ, GIT_INDEX_FILE=os.path.join(self.tree, ".git", "roadmap-index"),
                   GIT_AUTHOR_NAME="test", GIT_AUTHOR_EMAIL="test@example.com",
                   GIT_COMMITTER_NAME="test", GIT_COMMITTER_EMAIL="test@example.com")

        def run(*args, stdin=None):
            out = subprocess.run(["git", "-C", self.tree, *args], check=True, capture_output=True, text=True,
                                 env=env, input=stdin)
            return out.stdout.strip()

        run("read-tree", "--empty")
        for slug in slugs:
            blob = run("hash-object", "-w", "--stdin", stdin=STEP_JSON)
            run("update-index", "--add", "--cacheinfo", "100644,%s,roadmap/data/steps/%s.json" % (blob, slug))
        run("update-ref", "refs/remotes/origin/roadmap", run("commit-tree", run("write-tree"), "-m", "roadmap"))

    def printed_total(self, out, total):
        """True when the output prints `total` as a number of its own."""
        return re.search(r"(?<![\w.])%d(?![\w.])" % total, out) is not None

    def add_notes(self, *lines):
        """Commit `lines` as the new notes lines of a branch, on a base with no notes."""
        self.put(DEBT_NOTES, NOTES_HEAD)
        self.commit_base()
        self.put(DEBT_NOTES, NOTES_HEAD + "".join(lines))
        self.commit_change()

    def add_note(self, line):
        """Commit `line` as the one new notes line of a branch, on a base with no notes."""
        self.add_notes(line)

    def assert_only_the_scope_note_fails(self, out):
        """The scope note is refused by the Until rule, so its FAIL shows the notes were read. No other line fails."""
        self.assertTrue(self.failed_about(out, "scope-note"), out)
        self.assertEqual(len(fail_lines(out)), 1, out)

    def refused_notes(self, notes):
        """Add each {slug: text} of `notes` as a none note, and assert the check refuses each one and no other line."""
        self.add_notes(*[none_note(slug, text) for slug, text in notes.items()])
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        for slug in notes:
            self.assertTrue(self.failed_about(out, slug), out)
        self.assertEqual(len(fail_lines(out)), len(notes), out)  # one refusal per note, no other cause

    def passed_notes(self, notes):
        """Add each {slug: text} of `notes` as a none note beside the scope note, and assert the check refuses none."""
        self.add_notes(*[none_note(slug, text) for slug, text in notes.items()], SCOPE_NOTE)
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assert_only_the_scope_note_fails(out)

    def base_sha(self):
        return subprocess.run(["git", "-C", self.tree, "rev-parse", "origin/main"], check=True,
                              capture_output=True, text=True).stdout.strip()

    def head_sha(self):
        return subprocess.run(["git", "-C", self.tree, "rev-parse", "--short=7", "HEAD"], check=True,
                              capture_output=True, text=True).stdout.strip()

    def failed_about(self, out, *needles):
        """True when a FAIL line of the check names one of `needles`."""
        return any(any(n in line for n in needles) for line in fail_lines(out))

    # Positive controls first: a red case means nothing if the clean case fails.

    def test_default_passes_a_short_slug_in_decisions(self):
        self.put("decisions/" + OK)
        self.assert_passes("decisions/" + OK)

    def test_default_flags_long_slugs_in_decisions_and_debts(self):
        self.put("decisions/" + LONG)
        self.put("debts/" + LONG)
        rc, out = self.lint("decisions/" + LONG, "debts/" + LONG)
        self.assertEqual(rc, 1, out)
        self.assertEqual(flagged(out), ["decisions/" + LONG, "debts/" + LONG])

    def test_default_flags_long_slugs_in_debts(self):
        # debts/ holds slug-named records too, so the default run checks it with decisions/.
        self.put("debts/" + OK)
        self.assert_passes("debts/" + OK)
        self.put("debts/" + LONG)
        rc, out = self.lint("debts/" + LONG)
        self.assertEqual(rc, 1, out)
        self.assertEqual(flagged(out), ["debts/" + LONG])

    def test_default_leaves_other_folders_unchecked(self):
        self.put(DOCS + "/" + LONG)
        self.assert_passes(DOCS + "/" + LONG)

    def test_default_diff_flags_only_the_default_folders(self):
        self.commit_base()
        self.put("decisions/" + LONG)
        self.put(DOCS + "/" + LONG)
        self.commit_change()
        rc, out = self.lint()  # no file arguments: the diff against origin/main
        self.assertEqual(rc, 1, out)
        self.assertEqual(flagged(out), ["decisions/" + LONG])

    def test_backslash_path_is_checked_like_a_slash_path(self):
        # A Windows-style path names the same record, so its folder must still be read.
        self.assert_passes("decisions\\" + OK)
        rc, out = self.lint("decisions\\" + LONG)
        self.assertEqual(rc, 1, out)
        self.assertEqual(flagged(out), ["decisions\\" + LONG])

    def test_unknown_or_malformed_option_fails(self):
        # An option the check does not know must fail closed. Read as a file name, it would
        # pass, and the check would exit 0 having read nothing.
        self.put("decisions/" + OK)
        cases = [
            ["--dir=nope", "decisions/" + OK],
            ["--dir=", "decisions/" + OK],
            ["--dir=" + DOCS, DOCS + "/" + LONG],
            ["-dir=decisions", "decisions/" + OK],
            ["--dr", "decisions", "decisions/" + OK],
        ]
        for args in cases:
            with self.subTest(args=args):
                rc, out = self.lint(*args)
                self.assertNotEqual(rc, 0, out)
                self.assertNotIn("Traceback", out)

    def test_dot_slash_record_path_is_judged(self):
        self.assert_passes("./decisions/" + OK)
        rc, out = self.lint("./decisions/" + VERY_LONG)
        self.assertEqual(rc, 1, out)
        self.assertEqual(flagged(out), ["./decisions/" + VERY_LONG])

    def test_default_diff_reads_debts(self):
        self.commit_base()
        self.put("debts/" + LONG, FIXED_DEBT_TEXT)  # a valid Fix line, so this case names only the slug cause
        self.commit_change()
        rc, out = self.lint()  # no file arguments: the diff against origin/main
        self.assertEqual(rc, 1, out)
        self.assertEqual(flagged(out), ["debts/" + LONG])

    def test_feel_debt_deleted_with_no_device_check_fails(self):
        self.put(FEEL_DEBT, FEEL_TEXT)
        self.commit_base()
        self.delete(FEEL_DEBT)
        self.commit_change()
        rc, out = self.lint()  # no file arguments: the diff against origin/main
        self.assertEqual(rc, 1, out)
        self.assertIn("check_record_slugs: FAIL: feel-fix debt deleted with no device check: " + FEEL_DEBT,
                      out.splitlines())

    def test_feel_debt_deleted_with_a_device_check_passes(self):
        # Paired with an unchecked feel-fix in the same diff: the checked debt must not be named.
        self.put(CHECKED_DEBT, CHECKED_TEXT)
        self.put(FEEL_DEBT, FEEL_TEXT)
        self.commit_base()
        self.delete(CHECKED_DEBT, FEEL_DEBT)
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertEqual(flagged(out), [FEEL_DEBT], out)

    def test_plain_debt_deleted_passes(self):
        # Paired with an unchecked feel-fix in the same diff: the plain debt must not be named.
        self.put(PLAIN_DEBT, PLAIN_TEXT)
        self.put(FEEL_DEBT, FEEL_TEXT)
        self.commit_base()
        self.delete(PLAIN_DEBT, FEEL_DEBT)
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertEqual(flagged(out), [FEEL_DEBT], out)

    def test_files_given_mode_skips_the_feel_check(self):
        self.put(FEEL_DEBT, FEEL_TEXT)
        self.commit_base()
        self.delete(FEEL_DEBT)
        self.commit_change()
        rc, out = self.lint()  # the same change fails with no file arguments
        self.assertEqual(rc, 1, out)
        self.assert_passes(FEEL_DEBT)  # files given: git is not read, so the feel check does not run

    def test_feel_debt_renamed_out_of_the_debt_folder_fails(self):
        self.put(FEEL_DEBT, FEEL_TEXT)
        self.commit_base()
        self.move(FEEL_DEBT, "notes/scroll-jank.md")  # a rename is git's R, and it leaves the debt folder
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertIn("check_record_slugs: FAIL: feel-fix debt deleted with no device check: " + FEEL_DEBT,
                      out.splitlines())

    def test_checked_debt_renamed_inside_the_folder_is_not_flagged(self):
        # Paired with a rename out of the folder in the same diff: only that one is named.
        self.put(CHECKED_DEBT, CHECKED_TEXT)
        self.put(FEEL_DEBT, FEEL_TEXT)
        self.commit_base()
        self.move(CHECKED_DEBT, "debts/tap-lag-renamed.md")  # inside the folder: keeps its check, no fail
        self.move(FEEL_DEBT, "notes/scroll-jank.md")
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertEqual(flagged(out), [FEEL_DEBT], out)

    def test_feel_line_dropped_from_a_debt_fails_only_without_a_device_check(self):
        # Both debts drop their Feel line on the branch. Only the one with no device check on main is named.
        self.put(CHECKED_DEBT, CHECKED_TEXT)
        self.put(FEEL_DEBT, FEEL_TEXT)
        self.commit_base()
        self.put(CHECKED_DEBT, PLAIN_TEXT)
        self.put(FEEL_DEBT, PLAIN_TEXT)
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertEqual(flagged(out), [FEEL_DEBT], out)

    def test_device_check_lines_that_are_not_valid_count_as_no_check(self):
        # A valid check names simulator or device, then an ISO time with a zone. Each line here is not valid.
        lines = {
            "debts/pending-check.md": "**Device check.** pending",
            "debts/no-zone.md": "**Device check.** simulator, 2026-11-01T11:44:00",
            "debts/no-time.md": "**Device check.** simulator",
            "debts/bad-how.md": "**Device check.** tablet, 2026-11-01T11:44:00-06:00",
        }
        for rel, line in lines.items():
            self.put(rel, FEEL_TEXT + "\n" + line + "\n")
        self.commit_base()
        self.delete(*lines)
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertEqual(sorted(flagged(out)), sorted(lines), out)

    def test_bullet_markers_count_at_line_start(self):
        # The debt parts are bullets, so "- " before a marker counts. A marker inside a sentence does not.
        bullet = "# Bullet jank\n\n- **Feel.** yes\n"
        self.put(BULLET_DEBT, bullet)
        self.put(BULLET_CHECKED, bullet + "- **Device check.** simulator, 2026-11-01T11:44:00-06:00\n")
        self.put(MID_LINE, "# Mid line\n\nSee the note: **Feel.** yes\n")
        self.commit_base()
        self.delete(BULLET_DEBT, BULLET_CHECKED, MID_LINE)
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertEqual(flagged(out), [BULLET_DEBT], out)

    def test_failed_git_show_prints_unknown(self):
        self.put(FEEL_DEBT, FEEL_TEXT)
        self.commit_base()
        loose = self.loose_blob(FEEL_DEBT)
        # A packed blob would survive the removal, and git show would not fail, so the case would prove nothing.
        self.assertTrue(os.path.isfile(loose), loose)
        os.remove(loose)
        self.delete(FEEL_DEBT)
        self.commit_change()
        rc, out = self.lint()
        self.assertIn("check_record_slugs: UNKNOWN", out, out)
        self.assertEqual(rc, 0, out)  # locally an unknown is not red; CI reads it as red
        self.assertNotIn("feel-fix debt deleted", out)

    def test_debt_readme_edited_to_drop_a_feel_line_passes(self):
        self.put(DEBT_README, README_FEEL_TEXT)
        self.commit_base()
        self.put(DEBT_README, "# Debts\n\nOne debt per file.\n")  # drops the marker line
        self.commit_change()
        self.assert_passes()

    def test_debt_readme_reworded_away_from_a_feel_line_passes(self):
        self.put(DEBT_README, README_FEEL_TEXT)
        self.commit_base()
        self.put(DEBT_README, README_FEEL_TEXT.replace("**Feel.**", "**Feel:**"))  # rewords the marker
        self.commit_change()
        self.assert_passes()

    def test_debt_notes_deleted_with_a_feel_line_passes(self):
        self.put(DEBT_NOTES, NOTES_FEEL_TEXT)
        self.commit_base()
        self.delete(DEBT_NOTES)
        self.commit_change()
        self.assert_passes()

    def test_readme_and_notes_are_not_read_with_git_show(self):
        # With their blobs removed, git show fails on either file. No UNKNOWN means neither file was read.
        self.put(DEBT_README, README_FEEL_TEXT)
        self.put(DEBT_NOTES, NOTES_FEEL_TEXT)
        self.commit_base()
        for rel in (DEBT_README, DEBT_NOTES):
            loose = self.loose_blob(rel)
            self.assertTrue(os.path.isfile(loose), loose)
            os.remove(loose)
        self.put(DEBT_README, "# Debts\n\nOne debt per file.\n")
        self.delete(DEBT_NOTES)
        self.commit_change()
        rc, out = self.lint()
        self.assertNotIn("UNKNOWN", out)
        self.assertEqual(rc, 0, out)

    # Each line a branch adds to the notes file, and each new debt file, needs a Fix field: step:<slug> on
    # origin/roadmap, none with a listed reason, or already fixed on main with a sha. A missing read fails.

    def test_new_notes_line_without_a_fix_is_red(self):
        self.put(DEBT_NOTES, NOTES_HEAD)
        self.commit_base()
        self.put(DEBT_NOTES, NOTES_HEAD + NEW_NO_FIX)
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertTrue(self.failed_about(out, "new-note", DEBT_NOTES), out)

    def test_new_notes_line_with_a_prose_fix_is_red(self):
        self.put(DEBT_NOTES, NOTES_HEAD)
        self.commit_base()
        self.put(DEBT_NOTES, NOTES_HEAD + NEW_PROSE_FIX)
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertTrue(self.failed_about(out, "new-note", DEBT_NOTES), out)

    def test_step_fix_naming_a_step_absent_from_origin_roadmap_is_red(self):
        # HEAD holds alpha.json, so a check that reads the working tree would pass. origin/roadmap holds alpha-beta only.
        self.put(ALPHA_STEP, STEP_JSON)
        self.put(DEBT_NOTES, NOTES_HEAD)
        self.commit_base()
        self.roadmap("alpha-beta")
        self.put(DEBT_NOTES, NOTES_HEAD + NEW_ABSENT_STEP)
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertTrue(self.failed_about(out, "new-note", DEBT_NOTES), out)

    def test_none_reason_outside_the_list_is_red(self):
        self.put(DEBT_NOTES, NOTES_HEAD)
        self.commit_base()
        self.put(DEBT_NOTES, NOTES_HEAD + NEW_BAD_REASON)
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertTrue(self.failed_about(out, "new-note", DEBT_NOTES), out)

    def test_refusal_for_a_bad_reason_lists_the_allowed_reasons(self):
        # The refusal names each reason the check allows, so a writer can pick one from the refusal alone.
        self.add_note(NEW_BAD_REASON)
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertTrue(self.failed_about(out, "new-note", DEBT_NOTES), out)
        for reason in ("owner decides", "needs the Mac", "rare and harmless", "needs a Windows run"):
            self.assertIn(reason, out, "the refusal does not list the allowed reason: %s" % reason)

    def test_edited_old_notes_line_with_the_same_slug_passes(self):
        self.put(DEBT_NOTES, NOTES_HEAD + OLD_NOTE)
        self.commit_base()
        self.put(DEBT_NOTES, NOTES_HEAD + "- old-note: an old gap, reworded. Fix: pin the base.\n")
        self.commit_change()
        self.assert_passes()

    def test_untouched_old_notes_lines_pass(self):
        # A full base: 40 old lines, each with a prose Fix. The branch adds one valid line, and only that line is read.
        old = "".join("- old-note-%02d: an old gap. Fix: pin the base.\n" % n for n in range(40))
        self.put(DEBT_NOTES, NOTES_HEAD + old)
        self.commit_base()
        self.put(DEBT_NOTES, NOTES_HEAD + old + NEW_VALID_NONE)
        self.commit_change()
        self.assert_passes()

    def test_valid_step_and_none_forms_pass(self):
        self.put(DEBT_NOTES, NOTES_HEAD)
        self.commit_base()
        self.roadmap("alpha-beta")
        self.put(DEBT_NOTES, NOTES_HEAD + "".join(VALID_LINES))
        self.commit_change()
        self.assert_passes()

    def test_new_debt_file_without_a_fix_line_is_red(self):
        self.put(DEBT_NOTES, NOTES_HEAD)
        self.commit_base()
        self.put(NEW_DEBT, DEBT_NO_FIX)
        self.put(FIXED_DEBT, FIXED_DEBT_TEXT)  # the control: a valid Fix line in the same diff
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertEqual(flagged(out), [NEW_DEBT], out)

    def test_roadmap_read_failure_exits_nonzero_and_says_the_read_did_not_run(self):
        # No origin/roadmap ref: a step fix cannot be checked, so the check fails. It never passes.
        self.put(DEBT_NOTES, NOTES_HEAD)
        self.commit_base()
        self.put(DEBT_NOTES, NOTES_HEAD + NEW_VALID_STEP)
        self.commit_change()
        rc, out = self.lint()
        self.assertNotEqual(rc, 0, out)
        self.assertIn("did not run", out)
        self.assertNotIn("Traceback", out)

    def test_already_fixed_on_main_with_a_sha_passes(self):
        self.put(DEBT_NOTES, NOTES_HEAD)
        self.commit_base()
        sha = self.base_sha()[:7]
        self.put(DEBT_NOTES, NOTES_HEAD + "- fixed-note: a gap. Fix: already fixed on main %s\n" % sha)
        self.commit_change()
        self.assert_passes()

    def test_already_fixed_on_main_with_no_sha_is_red(self):
        self.put(DEBT_NOTES, NOTES_HEAD)
        self.commit_base()
        self.put(DEBT_NOTES, NOTES_HEAD + "- fixed-note: a gap. Fix: already fixed on main\n")
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertTrue(self.failed_about(out, "fixed-note", DEBT_NOTES), out)

    def test_already_fixed_on_main_with_a_made_up_sha_is_red(self):
        # 1234567 is hex, so the grammar reads it. No commit on main has it, so the Fix names no real commit.
        self.put(DEBT_NOTES, NOTES_HEAD)
        self.commit_base()
        self.put(DEBT_NOTES, NOTES_HEAD + "- fixed-note: a gap. Fix: already fixed on main 1234567\n")
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertTrue(self.failed_about(out, "fixed-note", DEBT_NOTES), out)

    def test_already_fixed_on_main_with_a_branch_only_sha_is_red(self):
        # The sha is a commit of this branch, not an ancestor of origin/main, so the Fix names no fix on main.
        self.put(DEBT_NOTES, NOTES_HEAD)
        self.commit_base()
        self.put("branch-only.txt", "only on the branch\n")
        self.commit_change()
        sha = self.head_sha()
        self.put(DEBT_NOTES, NOTES_HEAD + "- fixed-note: a gap. Fix: already fixed on main %s\n" % sha)
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertTrue(self.failed_about(out, "fixed-note", DEBT_NOTES), out)

    def test_already_fixed_on_an_older_main_commit_passes(self):
        # The sha is an ancestor of origin/main, not its tip: any commit on main is a real fix.
        self.put(DEBT_NOTES, NOTES_HEAD)
        self.commit_base()
        older = self.base_sha()[:7]
        self.put("later.txt", "a later commit on main\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "later")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.put(DEBT_NOTES, NOTES_HEAD + "- fixed-note: a gap. Fix: already fixed on main %s\n" % older)
        self.commit_change()
        self.assert_passes()

    def test_swapped_note_without_a_fix_is_red_under_diff_noprefix(self):
        # The swap keeps the unfixed count level, so only the diff reads the new line. With diff.noprefix the diff's file
        # headers carry no b/ prefix, and the added line must still be read.
        self.put(DEBT_NOTES, NOTES_HEAD + OLD_NOTE)
        self.commit_base()
        self.git("config", "diff.noprefix", "true")
        self.put(DEBT_NOTES, NOTES_HEAD + NEW_NO_FIX)
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertTrue(self.failed_about(out, "new-note", DEBT_NOTES), out)

    def test_swapped_note_with_a_fix_under_diff_noprefix_passes(self):
        # The control for the case above: the same swap and config, with a valid Fix on the new line, passes.
        self.put(DEBT_NOTES, NOTES_HEAD + OLD_NOTE)
        self.commit_base()
        self.git("config", "diff.noprefix", "true")
        self.put(DEBT_NOTES, NOTES_HEAD + NEW_VALID_NONE)
        self.commit_change()
        self.assert_passes()

    def test_none_reason_for_a_windows_run_passes(self):
        # A reason the coordinator added: a Windows run. Red until the check lists it.
        self.put(DEBT_NOTES, NOTES_HEAD)
        self.commit_base()
        self.put(DEBT_NOTES, NOTES_HEAD + "- win-note: a gap. Fix: none — needs a Windows run Until: 2026-11-20\n")
        self.commit_change()
        self.assert_passes()

    def test_lone_quote_and_comment_opener_in_the_note_text_do_not_hide_the_fix(self):
        # The apostrophe and the comment openers are text. The valid line passes; the prose line is red.
        self.put(DEBT_NOTES, NOTES_HEAD)
        self.commit_base()
        self.put(DEBT_NOTES, NOTES_HEAD
                 + "- quote-ok: Don't drop the lock (see #12 and /* the old block */). Fix: none — owner decides. "
                   "Until: 2026-11-20\n"
                 + "- quote-prose: Don't drop the lock, see // the old block. Fix: pin the base.\n")
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertTrue(self.failed_about(out, "quote-prose", DEBT_NOTES), out)
        self.assertFalse(self.failed_about(out, "quote-ok"), out)

    def test_bullet_fix_line_in_a_new_debt_file_passes(self):
        # A debt file's Fix line counts at column one or after one leading "- ", as its Feel line does.
        self.put(DEBT_NOTES, NOTES_HEAD)
        self.commit_base()
        self.roadmap("alpha-beta")
        self.put(NEW_DEBT, "# New debt\n\nWhat. A gap with a bullet fix.\n\n- Fix: step:alpha-beta\n")
        self.commit_change()
        self.assert_passes()

    def test_none_and_already_fixed_lines_pass_without_origin_roadmap(self):
        # Only a step line reads origin/roadmap. With no origin/roadmap ref, these two forms still pass.
        self.put(DEBT_NOTES, NOTES_HEAD)
        self.commit_base()
        fixed = "- fixed-note: a gap. Fix: already fixed on main %s\n" % self.base_sha()[:7]
        self.put(DEBT_NOTES, NOTES_HEAD + NEW_VALID_NONE + fixed)
        self.commit_change()
        self.assert_passes()

    # The ratchet: the notes bullets with no Fix of the new grammar may not grow. Both counts are read live from git.

    def test_ratchet_edit_that_removes_a_fix_and_raises_the_count_is_red(self):
        self.put(DEBT_NOTES, NOTES_HEAD + OLD_NOTE + KEPT_NOTE)
        self.commit_base()
        self.put(DEBT_NOTES, NOTES_HEAD + OLD_NOTE + "- kept-note: a gap, its Fix removed.\n")
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertTrue(self.printed_total(out, 2), out)  # HEAD holds two bullets with no new-grammar Fix

    def test_ratchet_red_prints_the_head_count(self):
        # Base holds one such bullet. Two edits drop a Fix, so HEAD holds three, and the total printed is three.
        self.put(DEBT_NOTES, NOTES_HEAD + OLD_NOTE + KEPT_NOTE + THIRD_NOTE)
        self.commit_base()
        self.put(DEBT_NOTES, NOTES_HEAD + OLD_NOTE + "- kept-note: a gap, its Fix removed.\n"
                 + "- third-note: a gap, its Fix removed.\n")
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertTrue(self.printed_total(out, 3), out)

    def test_ratchet_equal_count_passes(self):
        # One edit drops a Fix and another adds one. The count stays at one, so the branch passes.
        self.put(DEBT_NOTES, NOTES_HEAD + OLD_NOTE + KEPT_NOTE)
        self.commit_base()
        self.put(DEBT_NOTES, NOTES_HEAD + "- old-note: an old gap. Fix: already fixed on main 1a2b3c4\n"
                 + "- kept-note: a gap, its Fix removed.\n")
        self.commit_change()
        self.assert_passes()

    def test_ratchet_lower_count_passes(self):
        self.put(DEBT_NOTES, NOTES_HEAD + OLD_NOTE)
        self.commit_base()
        self.put(DEBT_NOTES, NOTES_HEAD + "- old-note: an old gap. Fix: already fixed on main 1a2b3c4\n")
        self.commit_change()
        self.assert_passes()

    # The Until date: each `Fix: none` line added or edited carries `Until: YYYY-MM-DD`, no more than 14 days from
    # today. Today is PINNED_TODAY, injected through FIXED_TODAY. An already-fixed line needs no date.

    def test_none_note_without_until_is_red(self):
        self.add_note("- new-note: a gap. Fix: none — owner decides\n")
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertTrue(self.failed_about(out, "new-note", DEBT_NOTES), out)

    def test_none_note_with_a_past_until_is_red(self):
        self.add_note("- new-note: a gap. Fix: none — owner decides. Until: 2026-11-06\n")
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertTrue(self.failed_about(out, "new-note", DEBT_NOTES), out)

    def test_none_note_dated_today_passes(self):
        self.add_note("- new-note: a gap. Fix: none — owner decides. Until: 2026-11-07\n")
        self.assert_passes()

    def test_none_note_at_the_cap_passes(self):
        self.add_note("- new-note: a gap. Fix: none — owner decides. Until: 2026-11-21\n")  # 14 days after today
        self.assert_passes()

    def test_none_note_past_the_cap_is_red(self):
        self.add_note("- new-note: a gap. Fix: none — owner decides. Until: 2026-11-22\n")  # 15 days after today
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertTrue(self.failed_about(out, "new-note", DEBT_NOTES), out)

    def test_edited_none_note_that_drops_its_until_is_red(self):
        self.put(DEBT_NOTES, NOTES_HEAD + "- old-note: an old gap. Fix: none — owner decides. Until: 2026-11-20\n")
        self.commit_base()
        self.put(DEBT_NOTES, NOTES_HEAD + "- old-note: an old gap, reworded. Fix: none — owner decides\n")
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertTrue(self.failed_about(out, "old-note", DEBT_NOTES), out)

    def test_untouched_old_none_note_with_a_past_until_passes(self):
        old = "- old-note: an old gap. Fix: none — owner decides. Until: 2026-01-01\n"
        self.put(DEBT_NOTES, NOTES_HEAD + old)
        self.commit_base()
        sha = self.base_sha()[:7]  # a real commit on origin/main, so the new line's Fix is valid
        self.put(DEBT_NOTES, NOTES_HEAD + old + "- new-note: a gap. Fix: already fixed on main %s\n" % sha)
        self.commit_change()
        self.assert_passes()

    # The cost and commit rule: a `Fix: none` note line whose text after the reason names a commit or a cost is
    # refused, unless check output follows it. Each red case adds one note, so its only FAIL is the one it names.

    def test_none_reason_naming_a_cost_is_red(self):
        self.add_note(COST_NOTE)
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertTrue(self.failed_about(out, "cost-note", DEBT_NOTES), out)

    def test_none_reason_naming_a_commit_is_red(self):
        self.add_note(COMMIT_NOTE)
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertTrue(self.failed_about(out, "commit-note", DEBT_NOTES), out)

    def test_each_cost_unit_after_a_none_reason_is_red(self):
        self.refused_notes({
            "unit-seconds": "rare and harmless: the call takes 1.3 s",
            "unit-millis": "rare and harmless: the call takes 200 ms",
            "unit-lines": "owner decides: the fix is 40 lines",
            "unit-kilobytes": "owner decides: the file is 3 KB",
            "unit-characters": "rare and harmless: 8,000 characters",
        })

    def test_each_complexity_word_after_a_none_reason_is_red(self):
        self.refused_notes({
            "complex-linear": "owner decides: the scan is linear",
            "complex-quadratic": "rare and harmless: the scan is quadratic",
            "complex-big-o": "owner decides: the scan is O(n^2)",
            "complex-n-log-n": "rare and harmless: the sort is O(n log n)",
        })

    def test_commit_of_seven_or_forty_hex_characters_after_a_none_reason_is_red(self):
        self.refused_notes({
            "commit-seven": "owner decides: the fix is in %s" % SEVEN,
            "commit-forty": "owner decides: the fix is in %s" % FORTY,
        })

    def test_check_output_without_its_verdict_word_is_red(self):
        # A backticked command alone is no check output, and a verdict word alone is none either.
        self.refused_notes({
            "check-no-verdict": "owner decides: 1.3 s per call, %s" % CHECK,
            "check-plain-verdict": "owner decides: 1.3 s per call, PASS",
        })

    def test_comment_opener_in_the_reason_text_does_not_hide_a_cost(self):
        # The "#" and "/*" are text. A checker that stops reading at a comment opener would miss the cost after them.
        self.add_notes("- quote-cost: Don't hold the lock. Fix: none — owner decides: see #2021 and /* the old "
                       "block */, then the call takes 1.3 s. Until: 2026-11-20\n")
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertTrue(self.failed_about(out, "quote-cost", DEBT_NOTES), out)

    def test_edited_old_line_that_gains_a_cost_is_red(self):
        self.put(DEBT_NOTES, NOTES_HEAD + none_note("old-cost", "owner decides"))
        self.commit_base()
        self.put(DEBT_NOTES, NOTES_HEAD + none_note("old-cost", "owner decides: the call takes 1.3 s"))
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertTrue(self.failed_about(out, "old-cost", DEBT_NOTES), out)

    # The controls. Each one shares a diff with the scope note, which the Until rule refuses on any build, so a
    # control is green on the old code and proves the notes were read before it claims the control passes.

    def test_none_reason_with_check_output_after_the_cost_passes(self):
        self.add_notes(
            none_note("check-cost", "rare and harmless: 8,000 characters take 1.3 s; %s PASS" % CHECK),
            none_note("check-commit", "owner decides: the open lane y (a52e7a0fe) makes it linear; %s green" % CHECK),
            SCOPE_NOTE)
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assert_only_the_scope_note_fails(out)

    def test_each_verdict_word_after_a_cost_is_check_output(self):
        notes = [none_note("verdict-%s" % word.lower(),
                           "rare and harmless: the call takes 1.3 s; %s %s" % (CHECK, word))
                 for word in ("PASS", "FAIL", "ok", "red", "green")]
        self.add_notes(*notes, SCOPE_NOTE)
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assert_only_the_scope_note_fails(out)

    def test_none_reason_naming_neither_a_commit_nor_a_cost_passes(self):
        self.add_notes(none_note("neither-note", "rare and harmless: the sort keeps equal keys in input order"),
                       SCOPE_NOTE)
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assert_only_the_scope_note_fails(out)

    def test_line_refs_issue_numbers_and_short_keys_after_a_none_reason_pass(self):
        self.add_notes(none_note("refs-note", "owner decides: see question_form.py:440-441, #2021, item 386, P5, "
                                              "c188 and d4"),
                       SCOPE_NOTE)
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assert_only_the_scope_note_fails(out)

    def test_hex_runs_that_name_no_commit_after_a_none_reason_pass(self):
        # Six hex characters, forty-one, digits only, letters only, and hex inside a longer word: none is a commit.
        notes = {
            "pass-six": "rare and harmless: the id is %s" % SIX,
            "pass-forty-one": "rare and harmless: the id is %s" % FORTY_ONE,
            "pass-digits-only": "owner decides: ticket 1234567 is open",
            "pass-letters-only": "owner decides: the set is defaced",
            "pass-inside-a-word": "owner decides: the build rc2a52e7a0fe9 is open",
        }
        self.add_notes(*[none_note(slug, text) for slug, text in notes.items()], SCOPE_NOTE)
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assert_only_the_scope_note_fails(out)

    def test_already_fixed_sha_not_on_main_is_refused_once(self):
        # The sha note is refused by the existing ancestry check. The cost rule must not refuse it a second time.
        self.put(DEBT_NOTES, NOTES_HEAD)
        self.commit_base()
        real = self.base_sha()[:7]
        self.put(DEBT_NOTES, NOTES_HEAD
                 + "- fixed-real: a gap. Fix: already fixed on main %s\n" % real
                 + "- fixed-made-up: a gap. Fix: already fixed on main 1a2b3c4\n")
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertTrue(self.failed_about(out, "fixed-made-up", DEBT_NOTES), out)  # the scope: the sha note is read
        self.assertFalse(self.failed_about(out, "fixed-real"), out)  # a sha on main is no refusal
        self.assertEqual(len(fail_lines(out)), 1, out)

    def test_step_fix_with_cost_text_after_it_passes(self):
        self.put(DEBT_NOTES, NOTES_HEAD)
        self.commit_base()
        self.roadmap("alpha-beta")
        self.put(DEBT_NOTES, NOTES_HEAD + "- step-cost: a gap. Fix: step:alpha-beta, 1.3 s per run\n" + SCOPE_NOTE)
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assert_only_the_scope_note_fails(out)

    def test_cost_before_the_reason_passes(self):
        # Only the text after the reason is read. A cost in the gap description is no claim about the Fix.
        self.add_notes("- before-cost: the call takes 1.3 s. Fix: none — owner decides. Until: 2026-11-20\n",
                       SCOPE_NOTE)
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assert_only_the_scope_note_fails(out)

    def test_untouched_full_base_of_costed_lines_passes(self):
        # A full base: 40 old lines, each with a cost and no check output. The branch adds one scope note only.
        old = "".join(none_note("old-cost-%02d" % n, "owner decides: the call takes 1.3 s") for n in range(40))
        self.put(DEBT_NOTES, NOTES_HEAD + old)
        self.commit_base()
        self.put(DEBT_NOTES, NOTES_HEAD + old + SCOPE_NOTE)
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assert_only_the_scope_note_fails(out)

    # Round 2 of the cite rule. Each case sits in the text after a listed reason. The refused cases name a cost the
    # digit form misses: spelled numbers, count units, unit gaps and case, and linear or quadratic in other forms.
    # The passing cases are honest check output and words that only look like a cost.

    def test_spelled_number_with_a_time_unit_after_a_none_reason_is_red(self):
        # "a second" is left out on purpose: it is ambiguous, as in "a second level".
        pairs = (("one", "hour"), ("two", "seconds"), ("three", "minutes"), ("four", "hours"), ("five", "seconds"),
                 ("six", "minutes"), ("seven", "hours"), ("eight", "seconds"), ("nine", "minutes"), ("ten", "minutes"))
        self.refused_notes({"spelled-%s" % word: "rare and harmless: the call takes %s %s" % (word, unit)
                            for word, unit in pairs})

    def test_count_unit_after_a_none_reason_is_red(self):
        self.refused_notes({
            "count-queries": "owner decides: the page runs 40 queries",
            "count-times": "rare and harmless: it runs 3 times",
            "count-calls": "owner decides: 12 calls per page",
            "count-x": "rare and harmless: the path is 2x slower",
        })

    def test_unit_gap_or_upper_case_unit_after_a_none_reason_is_red(self):
        self.refused_notes({
            "gap-milliseconds": "rare and harmless: the call takes 10 milliseconds",
            "gap-days": "owner decides: the job waits 3 days",
            "gap-hrs": "owner decides: the job takes 2 hrs",
            "gap-lower-kb": "rare and harmless: the file is 5 kb",
            "gap-mixed-kB": "rare and harmless: the file is 5 kB",
            "gap-mib": "owner decides: the cache is 5 MiB",
            "gap-upper-milliseconds": "rare and harmless: the call takes 10 MILLISECONDS",
        })

    def test_linear_or_quadratic_in_any_case_or_ly_form_after_a_none_reason_is_red(self):
        self.refused_notes({
            "word-scales-linearly": "owner decides: the scan scales linearly",
            "word-linear-capital": "rare and harmless: Linear in the note count",
            "word-quadratic-capital": "owner decides: Quadratic in the note count",
            "word-scales-quadratically": "rare and harmless: the scan scales quadratically",
        })

    def test_check_output_in_its_honest_forms_after_a_cost_passes(self):
        self.passed_notes({
            "honest-dash-pass": "rare and harmless: the call takes 1.3 s; `verdict bench` — pass",
            "honest-arrow-red": "owner decides: the call takes 1.3 s; `x` → red",
            "honest-colon-count": "owner decides: the run takes 1.3 s; `pytest -q`: 12 passed",
        })

    def test_a_second_level_and_a_linearizable_word_after_a_none_reason_pass(self):
        self.passed_notes({
            "word-second-level": "owner decides: a second level of cache",
            "word-linearizable": "rare and harmless: a linearizable store",
        })

    def test_long_digit_comma_reason_is_read_to_its_end(self):
        # The input shape only. P5 forbids a wall-clock assert, so the speed is not timed here. A run of "1," 8000 times
        # ends in a cost, so the check must read to the end and refuse. The same run with no cost must pass.
        run = "1," * 8000
        self.add_notes(none_note("long-red", "owner decides: %s then the call takes 1.3 s" % run),
                       none_note("long-pass", "owner decides: %s" % run))
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertTrue(self.failed_about(out, "long-red"), out)  # the scope: the long note is read to its end
        self.assertEqual(len(fail_lines(out)), 1, out)  # only the note with the cost is refused


class ImportTests(unittest.TestCase):
    """lint/compliance_probes.py imports the module and calls its functions on a child's root, so the command line
    runs only behind `__main__`. The command line itself stays as RecordSlugsTests pins it."""

    def test_importing_the_module_runs_no_check(self):
        spec = importlib.util.spec_from_file_location("record_slugs_under_import", MODULE)
        module = importlib.util.module_from_spec(spec)
        out = io.StringIO()
        # An option the command line refuses: run on import, it would print a FAIL line and exit.
        with mock.patch.object(sys, "argv", ["check_record_slugs.py", "--bogus"]), contextlib.redirect_stdout(out):
            try:
                spec.loader.exec_module(module)
            except SystemExit as err:
                self.fail("importing the module ran the check and exited %r: %s" % (err.code, out.getvalue().strip()))
        self.assertEqual(out.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
