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
import layout  # noqa: E402  the one home of where records live (lint/layout.json)
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
# A notes row is `- <slug>: text`. A slug on two rows is one finding recorded twice. The text of a row can hold a
# lone quote and comment openers, and a slug named mid-row is not a row.
NOTE_UNIQUE_TEXT = ("# Notes\n\n"
                    "- alpha-slug: the first row. Don't scroll `list` while it loads.\n"
                    "- beta-slug: another finding.\n"
                    "- gamma-slug: a third finding.\n")
NOTE_DUP_TEXT = ("# Notes\n\n"
                 "- alpha-slug: the first row. Don't scroll `list` while it loads.\n"
                 "- beta-slug: another finding.\n"
                 "- alpha-slug: the same finding, recorded again.\n")
NOTE_MID_ROW_TEXT = ("# Notes\n\n"
                     "- beta-slug: the cause is alpha-slug: unmeasured, see its row.\n"
                     "- gamma-slug: alpha-slug: is named again inside this row's text.\n"
                     "- alpha-slug: the only row that starts with the slug.\n"
                     "- delta-slug: see - alpha-slug: quoted.\n")  # `- ` before the slug in a row's text: no row
NOTE_OPENERS_TEXT = ("# Notes\n\n"
                     "- beta-slug: a row with `/*`, `//` and # in its text. Don't stop there.\n"
                     "- beta-slug: the second row, which makes the duplicate.\n")
NOTE_CASE_TEXT = NOTE_DUP_TEXT.replace("- alpha-slug: the same", "- Alpha-slug: the same")  # the slug in another case
NOTE_SPACE_TEXT = NOTE_DUP_TEXT.replace("- alpha-slug: the same", "- alpha-slug : the same")  # a space before the colon
FULL_UNIQUE = "# Notes\n\n" + "".join("- row-%03d-slug: finding %d.\n" % (i, i) for i in range(300))  # full size
FULL_DUP = FULL_UNIQUE + "- row-000-slug: the first row, written again at the end.\n"

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


def load_under_test():
    """The module under test, loaded without running its command line."""
    spec = importlib.util.spec_from_file_location("record_slugs_under_test", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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

    def break_git_show(self, ref_path):
        """Makes `git show origin/main:<ref_path>` fail. A packed blob would survive the removal, and git show
        would not fail, so the case would prove nothing."""
        loose = self.loose_blob(ref_path)
        self.assertTrue(os.path.isfile(loose), loose)
        os.remove(loose)

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
        self.put("debts/" + LONG)
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
        self.break_git_show(FEEL_DEBT)
        self.delete(FEEL_DEBT)
        self.commit_change()
        rc, out = self.lint()
        self.assertIn("check_record_slugs: UNKNOWN", out, out)
        self.assertEqual(rc, 0, out)  # locally an unknown is not red; CI reads it as red
        self.assertNotIn("feel-fix debt deleted", out)

    def test_duplicate_note_slug_still_fails_when_git_cannot_say(self):
        # The added files are unknown, but a duplicate note is a verdict of its own, so the exit is red.
        self.assertEqual(NOTE_DUP_TEXT.count("- alpha-slug:"), 2)  # scope: the notes hold the duplicate
        self.put(FEEL_DEBT, FEEL_TEXT)
        self.put(self.notes_path(), NOTE_DUP_TEXT)
        self.commit_base()
        self.break_git_show(FEEL_DEBT)
        self.delete(FEEL_DEBT)
        self.commit_change()
        rc, out = self.lint()
        self.assertNotEqual(rc, 0, "a duplicate notes slug exits 0 when git cannot say: " + out)
        self.assertIn("check_record_slugs: UNKNOWN", out, "git cannot say, but no UNKNOWN line: " + out)
        named = [line for line in out.splitlines() if line.startswith("check_record_slugs: FAIL:")]
        self.assertTrue(any("alpha-slug" in line for line in named), "no FAIL line names the duplicate: " + out)

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

    def notes_path(self):
        """The notes file the check reads: the first layout candidate, so a rolled-out repo's path is used too."""
        return layout.candidates(self.tree, "debt-notes")[0]

    def test_notes_with_unique_slugs_pass_the_check(self):
        # Green control: the same notes file with one more unique row passes, so the case below is the duplicate.
        notes = self.notes_path()
        self.put(notes, NOTE_UNIQUE_TEXT)
        self.commit_base()
        self.put(notes, NOTE_UNIQUE_TEXT + "- delta-slug: a fourth finding.\n")
        self.commit_change()
        self.assert_passes()

    def test_duplicate_note_slug_fails_the_check_and_names_it(self):
        notes = self.notes_path()
        self.put(notes, NOTE_UNIQUE_TEXT)
        self.commit_base()
        self.put(notes, NOTE_UNIQUE_TEXT + "- alpha-slug: the same finding, recorded again.\n")
        self.commit_change()
        rc, out = self.lint()  # no file arguments: the diff against origin/main
        self.assertNotIn("Traceback", out)
        self.assertNotEqual(rc, 0, out)
        named = [line for line in out.splitlines() if line.startswith("check_record_slugs: FAIL:")]
        self.assertTrue(any("alpha-slug" in line for line in named), out)
        self.assertFalse(any(other in line for line in named for other in ("beta-slug", "gamma-slug")), out)


class DuplicateNoteSlugTests(unittest.TestCase):
    """duplicate_note_slugs(text): the slugs that a notes text writes on two or more rows. No git, no temp tree."""

    def under_test(self):
        self.assertTrue(os.path.isfile(MODULE), "module absent: lint/check_record_slugs.py")
        # getattr, so a missing name fails this assert and not an ImportError.
        fn = getattr(load_under_test(), "duplicate_note_slugs", None)
        self.assertTrue(callable(fn), "lint/check_record_slugs.py has no duplicate_note_slugs(text): "
                                      "a slug written twice in the notes file is not refused")
        return fn

    def test_one_slug_written_twice_is_returned(self):
        fn = self.under_test()
        self.assertEqual(NOTE_DUP_TEXT.count("- alpha-slug:"), 2)  # scope: the fixture holds the two rows
        self.assertEqual(fn(NOTE_DUP_TEXT), ["alpha-slug"])

    def test_one_slug_written_twice_in_a_full_size_notes_file_is_returned(self):
        fn = self.under_test()
        self.assertEqual(FULL_DUP.count("- row-000-slug:"), 2)  # scope: 300 rows, the first one repeated at the end
        self.assertEqual(fn(FULL_DUP), ["row-000-slug"])

    def test_unique_slugs_return_nothing(self):
        fn = self.under_test()
        self.assertEqual(fn(NOTE_UNIQUE_TEXT), [])
        self.assertEqual(fn(FULL_UNIQUE), [])  # full size, no repeat
        self.assertEqual(fn("# Notes\n"), [])  # the empty state: a header and no rows
        self.assertEqual(fn(""), [])

    def test_slug_named_mid_row_is_not_counted(self):
        fn = self.under_test()
        starts = [line for line in NOTE_MID_ROW_TEXT.splitlines() if line.startswith("- alpha-slug:")]
        self.assertEqual(len(starts), 1)  # scope: one row starts with the slug
        self.assertEqual(NOTE_MID_ROW_TEXT.count("alpha-slug:"), 4)  # three more name it inside a row's text
        self.assertEqual(fn(NOTE_MID_ROW_TEXT), [], "a slug named inside a row's text is counted as a row")

    def test_comment_openers_and_a_lone_quote_in_row_text_do_not_hide_a_duplicate(self):
        fn = self.under_test()
        self.assertEqual(NOTE_OPENERS_TEXT.count("- beta-slug:"), 2)  # scope: the two rows
        self.assertEqual(fn(NOTE_OPENERS_TEXT), ["beta-slug"])

    def test_one_slug_in_two_cases_is_one_duplicate(self):
        fn = self.under_test()
        self.assertEqual(fn("# Notes\n\n- Alpha-slug: one row alone.\n- beta-slug: another row.\n"), [])  # control
        self.assertEqual(NOTE_CASE_TEXT.count("- alpha-slug:"), 1)  # scope: the two rows differ only in case
        self.assertEqual(NOTE_CASE_TEXT.count("- Alpha-slug:"), 1)
        self.assertEqual([slug.lower() for slug in fn(NOTE_CASE_TEXT)], ["alpha-slug"],
                         "`- Alpha-slug:` and `- alpha-slug:` are not counted as one duplicate")

    def test_one_slug_with_a_space_before_the_colon_is_one_duplicate(self):
        fn = self.under_test()
        self.assertEqual(fn("# Notes\n\n- alpha-slug : one row alone.\n- beta-slug: another row.\n"), [])  # control
        self.assertEqual(NOTE_SPACE_TEXT.count("- alpha-slug :"), 1)  # scope: one row has the space
        self.assertEqual(NOTE_SPACE_TEXT.count("- alpha-slug:"), 1)
        self.assertEqual(fn(NOTE_SPACE_TEXT), ["alpha-slug"],
                         "`- alpha-slug :` and `- alpha-slug:` are not counted as one duplicate")


class ImportTests(unittest.TestCase):
    """lint/compliance_probes.py imports the module and calls its functions on a child's root, so the command line
    runs only behind `__main__`. The command line itself stays as RecordSlugsTests pins it."""

    def test_importing_the_module_runs_no_check(self):
        out = io.StringIO()
        # An option the command line refuses: run on import, it would print a FAIL line and exit.
        with mock.patch.object(sys, "argv", ["check_record_slugs.py", "--bogus"]), contextlib.redirect_stdout(out):
            try:
                load_under_test()
            except SystemExit as err:
                self.fail("importing the module ran the check and exited %r: %s" % (err.code, out.getvalue().strip()))
        self.assertEqual(out.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
