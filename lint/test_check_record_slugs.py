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
import datetime
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
OLD_DEBT = "debts/old-debt.md"  # a debt file the base holds; a case edits it in place
FIXED_DEBT = "debts/fixed-debt.md"  # a new debt file with a valid Fix line, beside NEW_DEBT in the same diff
DEBT_NO_FIX = "# New debt\n\nWhat. A gap with no fix named.\n"
PINNED_TODAY = "2026-11-07"  # the date the suite pins: the check reads FIXED_TODAY, so no case reads the clock
PINNED_DATE = datetime.date.fromisoformat(PINNED_TODAY)  # the same date, for the cases that call a function directly
KEPT_NOTE = "- kept-note: a gap. Fix: already fixed on main 1a2b3c4\n"  # a bullet with a new-grammar Fix
THIRD_NOTE = "- third-note: a gap. Fix: already fixed on main 1a2b3c4\n"
SLUGLESS_OLD = "".join("- A gap number %d, nobody named its fix.\n" % n for n in range(8))  # 8 bullets on main: no slug, no Fix

RUN_FOLDER = None  # made in setUpModule, so an import leaks no folder


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


def flagged(out):
    """The paths the check named as FAIL: each FAIL line ends with its path."""
    return [line.rsplit(" ", 1)[1] for line in out.splitlines()
            if line.startswith("check_record_slugs: FAIL:")]


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

    def lint(self, *args, fixed_today=PINNED_TODAY):
        env = dict(os.environ)
        env.pop("CI", None)  # CI turns an unknown diff into red; these cases run locally
        env["FIXED_TODAY"] = fixed_today  # the check's date comes from here, never from the clock
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

    def commit_files(self, files, parent=None):
        """The sha of a commit of `files` (path -> text), built in a temp index so HEAD and the working tree do not
        move. With `parent`, the commit starts from that commit's tree and keeps its other files; without, it holds
        only `files`."""
        env = dict(os.environ, GIT_INDEX_FILE=os.path.join(self.tree, ".git", "temp-index"),
                   GIT_AUTHOR_NAME="test", GIT_AUTHOR_EMAIL="test@example.com",
                   GIT_COMMITTER_NAME="test", GIT_COMMITTER_EMAIL="test@example.com")

        def run(*args, stdin=None):
            out = subprocess.run(["git", "-C", self.tree, *args], check=True, capture_output=True, text=True,
                                 env=env, input=stdin)
            return out.stdout.strip()

        run("read-tree", parent or "--empty")
        for rel, text in files.items():
            blob = run("hash-object", "-w", "--stdin", stdin=text)
            run("update-index", "--add", "--cacheinfo", "100644,%s,%s" % (blob, rel))
        return run("commit-tree", run("write-tree"), *(["-p", parent] if parent else []), "-m", "test commit")

    def roadmap(self, *slugs):
        """Point refs/remotes/origin/roadmap at a commit that holds one step file for each slug."""
        files = {"roadmap/data/steps/%s.json" % slug: STEP_JSON for slug in slugs}
        self.git("update-ref", "refs/remotes/origin/roadmap", self.commit_files(files))

    def main_moves_to(self, rel, text):
        """Move origin/main one commit on, with `rel` set to `text`. Its other files stay as they were, and a branch's
        merge base stays where it was."""
        self.git("update-ref", "refs/remotes/origin/main", self.commit_files({rel: text}, parent=self.base_sha()))

    def printed_total(self, out, total):
        """True when the output prints `total` as a number of its own."""
        return re.search(r"(?<![\w.])%d(?![\w.])" % total, out) is not None

    def add_note(self, line):
        """Commit `line` as the one new notes line of a branch, on a base with no notes."""
        self.put(DEBT_NOTES, NOTES_HEAD)
        self.commit_base()
        self.put(DEBT_NOTES, NOTES_HEAD + line)
        self.commit_change()

    def base_sha(self):
        return subprocess.run(["git", "-C", self.tree, "rev-parse", "origin/main"], check=True,
                              capture_output=True, text=True).stdout.strip()

    def head_sha(self):
        return subprocess.run(["git", "-C", self.tree, "rev-parse", "--short=7", "HEAD"], check=True,
                              capture_output=True, text=True).stdout.strip()

    def commit_names(self):
        """The paths HEAD's commit adds or changes, sorted: the scope a case checks before it calls the module."""
        out = subprocess.run(["git", "-C", self.tree, "show", "--name-only", "--format=", "HEAD"], check=True,
                             capture_output=True, text=True).stdout
        return sorted(line for line in out.splitlines() if line)

    def renames(self):
        """The status lines of the diff from origin/main to HEAD, with rename detection: one line per changed path."""
        out = subprocess.run(["git", "-C", self.tree, "diff", "--name-status", "-M", "origin/main", "HEAD"],
                             check=True, capture_output=True, text=True).stdout
        return [line for line in out.splitlines() if line]

    def load(self):
        """The check's module, imported from this case's tree. The import binds this tree's `layout`, not one an
        earlier case left in sys.modules, so each case reads its own folders."""
        spec = importlib.util.spec_from_file_location("record_slugs_probe",
                                                      os.path.join(self.tree, "lint", "check_record_slugs.py"))
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(sys.modules):
            spec.loader.exec_module(module)
        return module

    def failed_about(self, out, *needles):
        """True when a FAIL line of the check names one of `needles`."""
        return any(line.startswith("check_record_slugs: FAIL:") and any(n in line for n in needles)
                   for line in out.splitlines())

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

    def test_lone_double_quote_before_the_fix_does_not_hide_it(self):
        # A lone " is text, as a lone ' is. The second " after the Fix must not pair with the first and blank the Fix.
        self.put(DEBT_NOTES, NOTES_HEAD)
        self.commit_base()
        self.roadmap("alpha-beta")
        self.put(DEBT_NOTES, NOTES_HEAD
                 + '- inch-ok: a 12" panel gap. Fix: step:alpha-beta, see "the old note".\n'
                 + '- inch-prose: a 12" panel gap, see the old block. Fix: pin the base.\n')
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertTrue(self.failed_about(out, "inch-prose", DEBT_NOTES), out)
        self.assertFalse(self.failed_about(out, "inch-ok"),
                         "a lone quote before the Fix hid the valid Fix on its line: " + out)

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

    def test_fix_only_inside_a_code_span_does_not_pass(self):
        self.put(DEBT_NOTES, NOTES_HEAD)
        self.commit_base()
        self.roadmap("alpha-beta")  # the step is real, so only the code span decides the line
        self.put(DEBT_NOTES, NOTES_HEAD + "- code-note: a gap, Don't ship it: `Fix: step:alpha-beta`.\n")
        self.commit_change()
        rc, out = self.lint()
        self.assertTrue(self.failed_about(out, "code-note", DEBT_NOTES),
                        "a Fix inside a code span passed as the line's field: " + out)
        self.assertEqual(rc, 1, out)

    def test_invalid_reason_then_a_quoted_valid_fix_is_red(self):
        self.put(DEBT_NOTES, NOTES_HEAD)
        self.commit_base()
        self.roadmap("alpha-beta")
        self.put(DEBT_NOTES, NOTES_HEAD + "- quoted-note: a gap. Fix: none — someday. Until: 2026-11-20 "
                 "(was \"Fix: step:alpha-beta\")\n")
        self.commit_change()
        rc, out = self.lint()
        self.assertTrue(self.failed_about(out, "quoted-note", DEBT_NOTES),
                        "a quoted valid Fix stood in for the line's invalid one: " + out)
        self.assertEqual(rc, 1, out)

    def test_valid_fix_then_a_quoted_invalid_form_passes(self):
        self.put(DEBT_NOTES, NOTES_HEAD)
        self.commit_base()
        self.roadmap("alpha-beta")
        self.put(DEBT_NOTES, NOTES_HEAD + "- quoted-ok: a gap. Fix: step:alpha-beta (the old line said "
                 "\"Fix: pin the base\")\n")
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 0, "a valid Fix was refused for a quoted form after it: " + out)

    def test_fix_none_in_a_fenced_block_is_not_the_debt_field(self):
        self.put(DEBT_NOTES, NOTES_HEAD)
        self.commit_base()
        self.put(NEW_DEBT, "# New debt\n\nWhat. A gap with no fix named.\n\n```\nFix: none -- owner decides\n```\n")
        self.put(FIXED_DEBT, FIXED_DEBT_TEXT)  # the control: a valid Fix line in the same diff
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(flagged(out), [NEW_DEBT],
                         "a Fix inside a fenced block passed as the debt's field: " + out)
        self.assertEqual(rc, 1, out)

    def test_debt_file_arriving_by_rename_is_checked(self):
        self.put("notes/gap-a.md", DEBT_NO_FIX)  # no Fix line; it reaches the debt folder by a rename
        self.put("notes/gap-b.md", FIXED_DEBT_TEXT)  # the control: a valid Fix, moved the same way
        self.commit_base()
        self.move("notes/gap-a.md", "debts/gap-a.md")
        self.move("notes/gap-b.md", "debts/gap-b.md")
        self.commit_change()
        self.assertTrue(self.renames() and all(line.startswith("R") for line in self.renames()),
                        "scope: both debt files must arrive by rename, got %r" % self.renames())
        rc, out = self.lint()
        self.assertEqual(flagged(out), ["debts/gap-a.md"],
                         "a debt file that arrived by rename was not checked: " + out)
        self.assertEqual(rc, 1, out)

    def test_new_bullet_in_a_renamed_notes_file_is_checked(self):
        base = NOTES_HEAD + "".join("- old-note-%02d: an old gap. Fix: pin the base.\n" % n for n in range(10))
        self.put(DEBT_NOTES, base)
        self.commit_base()
        self.move(DEBT_NOTES, "notes/notes.md")  # the commit renames the notes file out of its folder ...
        self.put("notes/notes.md", base + NEW_NO_FIX)  # ... and adds a bullet with no Fix to it
        self.commit_change()
        self.assertTrue(self.renames() and all(line.startswith("R") for line in self.renames()),
                        "scope: the notes file must arrive by rename, got %r" % self.renames())
        rc, out = self.lint()
        self.assertTrue(self.failed_about(out, "new-note"),
                        "a bullet added in a renamed notes file was not checked: " + out)
        self.assertEqual(rc, 1, out)

    def test_notes_file_renamed_inside_the_debt_folder_passes(self):
        # A pure rename adds no note: the bullets are the base's own, and the notes file is no debt.
        self.put(DEBT_NOTES, NOTES_HEAD + "".join(VALID_LINES))
        self.commit_base()
        self.move(DEBT_NOTES, "debts/notes-old.md")
        self.commit_change()
        self.assertTrue(self.renames() and all(line.startswith("R") for line in self.renames()),
                        "scope: the notes file must arrive by rename, got %r" % self.renames())
        rc, out = self.lint()
        self.assertEqual(rc, 0, "a notes file renamed inside the debt folder was read as a debt file: " + out)

    def test_notes_file_renamed_inside_the_debt_folder_with_valid_fix_bullets_passes(self):
        # The renamed file's new bullet carries a valid step Fix, so it passes, and the rename itself is no debt.
        self.put(DEBT_NOTES, NOTES_HEAD + "".join(VALID_LINES))
        self.commit_base()
        self.roadmap("alpha-beta")
        self.move(DEBT_NOTES, "debts/notes-old.md")
        self.put("debts/notes-old.md", NOTES_HEAD + "".join(VALID_LINES) + NEW_VALID_STEP)
        self.commit_change()
        self.assertTrue(self.renames() and all(line.startswith("R") for line in self.renames()),
                        "scope: the notes file must arrive by rename, got %r" % self.renames())
        rc, out = self.lint()
        self.assertEqual(rc, 0, "a notes file renamed inside the debt folder, with valid Fix bullets, was refused: " + out)

    def test_notes_file_renamed_inside_the_debt_folder_still_judges_a_bare_bullet(self):
        # The control for the two cases above: a bullet with no Fix that the renamed file adds is still red.
        self.put(DEBT_NOTES, NOTES_HEAD + "".join(VALID_LINES))
        self.commit_base()
        self.move(DEBT_NOTES, "debts/notes-old.md")
        self.put("debts/notes-old.md", NOTES_HEAD + "".join(VALID_LINES) + NEW_NO_FIX)
        self.commit_change()
        rc, out = self.lint()
        self.assertTrue(self.failed_about(out, "new-note"),
                        "a bullet with no Fix added in a renamed notes file passed: " + out)
        self.assertEqual(rc, 1, out)

    def test_numbered_bullet_without_a_fix_is_red(self):
        self.put(DEBT_NOTES, NOTES_HEAD)
        self.commit_base()
        self.put(DEBT_NOTES, NOTES_HEAD + "1. new-note: a gap nobody named.\n")
        self.commit_change()
        rc, out = self.lint()
        self.assertTrue(self.failed_about(out, "new-note", DEBT_NOTES),
                        "a numbered bullet with no Fix was not read as a note line: " + out)
        self.assertEqual(rc, 1, out)

    def test_indented_bullet_without_a_fix_is_red(self):
        self.put(DEBT_NOTES, NOTES_HEAD)
        self.commit_base()
        self.put(DEBT_NOTES, NOTES_HEAD + "  - new-note: a gap nobody named.\n")
        self.commit_change()
        rc, out = self.lint()
        self.assertTrue(self.failed_about(out, "new-note", DEBT_NOTES),
                        "an indented bullet with no Fix was not read as a note line: " + out)
        self.assertEqual(rc, 1, out)

    def test_dashless_bullet_without_a_fix_is_red(self):
        self.put(DEBT_NOTES, NOTES_HEAD)
        self.commit_base()
        self.put(DEBT_NOTES, NOTES_HEAD + "-new-note: a gap nobody named.\n")
        self.commit_change()
        rc, out = self.lint()
        self.assertTrue(self.failed_about(out, "new-note", DEBT_NOTES),
                        "a bullet with no space after its dash was not read as a note line: " + out)
        self.assertEqual(rc, 1, out)

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

    def test_none_note_with_a_date_that_is_not_real_is_red(self):
        self.add_note("- new-note: a gap. Fix: none — owner decides. Until: 2026-02-30\n")
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertTrue(self.failed_about(out, "new-note", DEBT_NOTES), out)

    def test_ratchet_at_full_size_edit_that_removes_a_fix_is_red(self):
        # Full size: 1,500 bullets, every third with no Fix, so 500 count at the base. One edit drops a Fix: 501.
        lines = [NOTES_HEAD] + [
            "- full-%04d: a gap, no fix named.\n" % n if n % 3 == 0
            else "- full-%04d: a gap. Fix: already fixed on main 1a2b3c4\n" % n for n in range(1500)]
        self.put(DEBT_NOTES, "".join(lines))
        self.commit_base()
        lines[2] = "- full-0001: a gap, its Fix removed.\n"  # lines[1] is full-0000, so lines[2] is full-0001
        self.put(DEBT_NOTES, "".join(lines))
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertTrue(self.printed_total(out, 501), out)

    def test_ratchet_branch_forked_before_main_lowered_its_count_is_not_blamed(self):
        # The merge base holds two bullets with no Fix. The branch rewords one and keeps two. Then origin/main moves on
        # and fixes the other, so main holds one. The branch is judged against its merge base: two, not one.
        self.put(DEBT_NOTES, NOTES_HEAD + OLD_NOTE + "- second-note: a gap, no fix named.\n")
        self.commit_base()
        merge_base = self.base_sha()[:7]
        self.put(DEBT_NOTES, NOTES_HEAD + "- old-note: an old gap, reworded. Fix: pin the base.\n"
                 + "- second-note: a gap, no fix named.\n")
        self.commit_change()
        self.main_moves_to(DEBT_NOTES, NOTES_HEAD + OLD_NOTE
                           + "- second-note: a gap. Fix: already fixed on main %s\n" % merge_base)
        self.assert_passes()

    def test_ratchet_counts_a_numbered_bullet_with_no_fix(self):
        self.put(DEBT_NOTES, NOTES_HEAD + OLD_NOTE)  # one bullet with no valid Fix on main
        self.commit_base()
        self.put(DEBT_NOTES, NOTES_HEAD + OLD_NOTE + "1. new-note: a gap nobody named.\n")
        self.commit_change()
        rc, out = self.lint()
        self.assertIn("notes with no valid Fix: 2 now, 1 at the merge base", out,
                      "the ratchet did not count a numbered bullet: " + out)
        self.assertEqual(rc, 1, out)

    def test_ratchet_counts_an_indented_bullet_with_no_fix(self):
        self.put(DEBT_NOTES, NOTES_HEAD + OLD_NOTE)
        self.commit_base()
        self.put(DEBT_NOTES, NOTES_HEAD + OLD_NOTE + "  - new-note: a gap nobody named.\n")
        self.commit_change()
        rc, out = self.lint()
        self.assertIn("notes with no valid Fix: 2 now, 1 at the merge base", out,
                      "the ratchet did not count an indented bullet: " + out)
        self.assertEqual(rc, 1, out)

    def test_ratchet_counts_a_dashless_bullet_with_no_fix(self):
        self.put(DEBT_NOTES, NOTES_HEAD + OLD_NOTE)
        self.commit_base()
        self.put(DEBT_NOTES, NOTES_HEAD + OLD_NOTE + "-new-note: a gap nobody named.\n")
        self.commit_change()
        rc, out = self.lint()
        self.assertIn("notes with no valid Fix: 2 now, 1 at the merge base", out,
                      "the ratchet did not count a bullet with no space after its dash: " + out)
        self.assertEqual(rc, 1, out)

    def test_reworded_old_bullet_with_no_slug_passes(self):
        # A reword of a slugless bullet on main keeps the count at eight, so the branch edits an old line.
        self.put(DEBT_NOTES, NOTES_HEAD + SLUGLESS_OLD)
        self.commit_base()
        self.put(DEBT_NOTES, NOTES_HEAD + SLUGLESS_OLD.replace("gap number 0, nobody", "gap number 0, no one"))
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 0, "a reword of an old bullet with no slug was refused: " + out)

    def test_new_bullet_with_no_slug_and_no_fix_is_still_red(self):
        # Control for the reword case: a ninth such bullet is new, so the count grows and the branch is red.
        self.put(DEBT_NOTES, NOTES_HEAD + SLUGLESS_OLD)
        self.commit_base()
        self.put(DEBT_NOTES, NOTES_HEAD + SLUGLESS_OLD + "- A gap number 8, nobody named its fix.\n")
        self.commit_change()
        rc, out = self.lint()
        self.assertIn("notes with no valid Fix: 9 now, 8 at the merge base", out, out)
        self.assertEqual(rc, 1, out)

    # The functions the roadmap's upkeep list, report_guard.py and the check's own run read. Each case below holds
    # one branch of one of them, read directly, so the branch's own result is what the case asserts.

    def test_commit_fixes_reads_a_new_note_line_and_a_new_debt_file(self):
        self.put(DEBT_NOTES, NOTES_HEAD)
        self.commit_base()
        self.put(DEBT_NOTES, NOTES_HEAD + NEW_VALID_NONE)
        self.put(NEW_DEBT, "# New debt\n\nWhat. A gap with a fix named.\n\nFix: step:alpha-beta\n")
        self.commit_change()
        self.assertEqual(self.commit_names(), sorted([DEBT_NOTES, NEW_DEBT]))  # scope: the commit adds these two
        entries = self.load().commit_fixes(self.tree, self.head_sha())
        self.assertIsInstance(entries, list, "commit_fixes returned %r, not a list" % (entries,))
        self.assertCountEqual(entries, [
            (DEBT_NOTES, "new-note", [("none", "owner decides")]),
            (NEW_DEBT, NEW_DEBT, [("step", "alpha-beta")]),
        ])

    def test_commit_fixes_skips_a_debt_file_the_commit_only_edits(self):
        self.put(OLD_DEBT, "# Old debt\n\nWhat. A gap.\n")
        self.commit_base()
        self.put(OLD_DEBT, "# Old debt\n\nWhat. A gap.\n\nFix: none — owner decides\n")
        self.commit_change()
        self.assertEqual(self.commit_names(), [OLD_DEBT])  # scope: the commit edits one old debt file
        entries = self.load().commit_fixes(self.tree, self.head_sha())
        self.assertIsInstance(entries, list, "commit_fixes returned %r, not a list" % (entries,))
        self.assertEqual(entries, [], "commit_fixes read the Fix line of a debt file the commit did not create")

    def test_expired_notes_lists_only_none_bullets_past_their_until(self):
        # Five lines: one expired none bullet, and four that are not: a none bullet dated after today, a step bullet
        # with an old date, a line that is not a bullet, and a none bullet with no date.
        self.put(DEBT_NOTES,
                 "- past-none: a gap. Fix: none — owner decides. Until: 2026-11-01\n"
                 "- future-none: a gap. Fix: none — owner decides. Until: 2026-11-20\n"
                 "- old-step: a gap. Fix: step:alpha-beta. Until: 2026-11-01\n"
                 "Prose line, not a bullet: a gap. Fix: none — owner decides. Until: 2026-11-01\n"
                 "- undated-none: a gap. Fix: none — owner decides\n")
        self.assertTrue(os.path.isfile(os.path.join(self.tree, *DEBT_NOTES.split("/"))))  # scope: the notes file exists
        rows = self.load().expired_notes(self.tree, PINNED_DATE)
        self.assertIsInstance(rows, list, "expired_notes returned %r, not a list" % (rows,))
        self.assertEqual(rows, [(DEBT_NOTES, "past-none", datetime.date(2026, 11, 1))])

    def test_expired_notes_with_no_notes_file_lists_nothing_and_reads_no_file(self):
        self.put(DEBT_README, "# Debts\n\nOne debt per file.\n")  # the folder exists, its notes file does not
        self.assertFalse(os.path.exists(os.path.join(self.tree, *DEBT_NOTES.split("/"))))  # scope: no notes file
        try:
            rows = self.load().expired_notes(self.tree, PINNED_DATE)
        except OSError as err:
            self.fail("expired_notes opened a notes file that is not there: %s" % err)
        self.assertEqual(rows, [])

    def test_ratchet_is_not_read_when_the_branch_leaves_the_notes_file_alone(self):
        self.put(DEBT_NOTES, NOTES_HEAD + NEW_NO_FIX)  # a bullet with no Fix at HEAD: it would count if read
        self.put(PLAIN_DEBT, PLAIN_TEXT)
        self.commit_base()
        self.put(PLAIN_DEBT, "# Stale link\n\nA plain debt, reworded.\n")
        self.commit_change()
        moved = [("M", PLAIN_DEBT, PLAIN_DEBT)]
        touched = [path for _status, old, new in moved for path in (old, new)]
        self.assertNotIn(DEBT_NOTES, touched)  # scope: the branch touches no notes file
        self.assertIsNone(self.load().notes_ratchet(self.tree, [], moved))

    def test_until_problem_returns_an_empty_string_for_a_line_that_passes(self):
        # The docstring says a passing line gives ''. A step Fix needs no date; a none line dated today passes.
        module = self.load()
        self.assertEqual(module.until_problem("- step-note: a gap. Fix: step:alpha-beta\n", PINNED_DATE), "")
        self.assertEqual(module.until_problem("- owner-note: a gap. Fix: none — owner decides. Until: 2026-11-07\n",
                                              PINNED_DATE), "")

    def test_a_fixed_today_that_is_not_a_date_is_red_with_its_named_cause(self):
        self.add_note(NEW_VALID_NONE)
        rc, out = self.lint(fixed_today="not-a-date")
        self.assertEqual(rc, 1, out)
        self.assertNotIn("Traceback", out)
        self.assertIn("FIXED_TODAY is not an ISO date", out)

    def test_an_already_fixed_check_prints_only_its_own_lines(self):
        # git prints a sha for each rev-parse of the Fix. Every line the check prints must carry its own prefix.
        self.put(DEBT_NOTES, NOTES_HEAD)
        self.commit_base()
        sha = self.base_sha()[:7]
        self.put(DEBT_NOTES, NOTES_HEAD + "- fixed-note: a gap. Fix: already fixed on main %s\n" % sha)
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 0, out)
        for line in out.splitlines():
            self.assertTrue(line.startswith("check_record_slugs:"), "a line the check did not print: %r" % line)


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
