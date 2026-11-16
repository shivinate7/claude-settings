#!/usr/bin/env python3
"""Cases for lint/check_record_slugs.py. Standard library only.

    python3 lint/test_check_record_slugs.py

A record file that a change adds must have a slug of 32 characters or fewer. The check reads
decisions/ and debts/ from the diff, or the files it is given.

A section file under tests/guard/ has a `# section <n>` header on its first line. Its name is `s<n>-<slug>.py`,
and a name that does not read so is refused. Its number must be its name's number, and no other section file may
hold it. The tree is read, not only the diff, and file arguments do not skip that read.

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
SECTIONS = "tests/guard"  # the section folder, as hooks/test_guard.py's SECTION_DIR names it


def section_text(n, body=""):
    """A section file: its first line is the `# section <n>` header that test_guard.py reads."""
    return "# section %d\n%s" % (n, body)


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

    # Section files. Git merges two branches' new section files clean, so the check reads the whole
    # tree. Each red names its cause alone.

    def assert_tracked(self, *rels):
        """Scope first: the section files a case names are in the committed tree before the check reads it."""
        listed = subprocess.run(["git", "-C", self.tree, "ls-files", "--", SECTIONS], capture_output=True,
                                text=True, encoding="utf-8", check=True).stdout.split()
        for rel in rels:
            self.assertIn(rel, listed, "scope: %s is not in the committed tree, so the check has nothing to read" % rel)

    def test_two_section_files_on_one_number_fail(self):
        # The shape git merges clean: main holds section 43500, and a branch adds a second file on that number.
        self.put(SECTIONS + "/s43500-a.py", section_text(43500))
        self.commit_base()
        self.put(SECTIONS + "/s43500-b.py", section_text(43500))
        self.commit_change()
        self.assert_tracked(SECTIONS + "/s43500-a.py", SECTIONS + "/s43500-b.py")
        rc, out = self.lint()
        self.assertEqual(rc, 1, "two section files on number 43500 must be refused:\n" + out)
        self.assertEqual(sorted(flagged(out)), [SECTIONS + "/s43500-a.py", SECTIONS + "/s43500-b.py"], out)

    def test_section_file_named_for_another_number_fails(self):
        # The name says 43501 and the header says 43500, so the file is judged under the wrong number.
        self.commit_base()
        self.put(SECTIONS + "/s43501-x.py", section_text(43500))
        self.commit_change()
        self.assert_tracked(SECTIONS + "/s43501-x.py")
        rc, out = self.lint()
        self.assertEqual(rc, 1, "a section file whose name disagrees with its header must be refused:\n" + out)
        self.assertEqual(flagged(out), [SECTIONS + "/s43501-x.py"], out)

    def test_duplicate_already_on_main_fails_a_run_with_no_diff(self):
        # The tree is checked, not only the diff: a run that adds nothing still refuses a pair main already holds.
        self.put(SECTIONS + "/s43500-a.py", section_text(43500))
        self.put(SECTIONS + "/s43500-b.py", section_text(43500))
        self.commit_base()  # HEAD is origin/main, so the diff is empty
        self.assert_tracked(SECTIONS + "/s43500-a.py", SECTIONS + "/s43500-b.py")
        rc, out = self.lint()
        self.assertEqual(rc, 1, "a pair on one number already on the base must be refused:\n" + out)
        self.assertEqual(sorted(flagged(out)), [SECTIONS + "/s43500-a.py", SECTIONS + "/s43500-b.py"], out)

    def test_distinct_section_numbers_pass(self):
        # The green control beside the reds: two files, two numbers, each name agreeing with its header.
        self.put(SECTIONS + "/s43500-a.py", section_text(43500))
        self.commit_base()
        self.put(SECTIONS + "/s43501-b.py", section_text(43501))
        self.commit_change()
        self.assert_tracked(SECTIONS + "/s43500-a.py", SECTIONS + "/s43501-b.py")
        self.assert_passes()

    def test_zero_padded_name_agrees_with_its_header(self):
        # The real folder holds s00442 under `# section 442`. The name and the header agree as numbers.
        self.put(SECTIONS + "/s00442-misc.py", section_text(442))
        self.commit_base()
        self.put(SECTIONS + "/s43501-b.py", section_text(43501))
        self.commit_change()
        self.assert_tracked(SECTIONS + "/s00442-misc.py", SECTIONS + "/s43501-b.py")
        self.assert_passes()

    def test_header_is_the_first_line_only(self):
        # Scanner traps (building-scanner-respects-strings): a `# section` line inside a string is not a
        # header, and a lone quote in the text is no error. Matching every line would count 43500 twice.
        self.put(SECTIONS + "/s43500-a.py", section_text(43500))
        self.commit_base()
        body = ('ONE = "# section 43500"\n'
                'TEXT = """\n'
                '# section 43500\n'
                "Don't count this line.\n"
                '"""\n')
        self.put(SECTIONS + "/s43502-trap.py", section_text(43502, body))
        self.commit_change()
        self.assert_tracked(SECTIONS + "/s43500-a.py", SECTIONS + "/s43502-trap.py")
        self.assert_passes()

    def add_section_in_change(self, rel, header):
        """A base with no section file, then a change that adds `rel` with `# section <header>`. Scope is checked."""
        self.commit_base()
        self.put(rel, section_text(header))
        self.commit_change()
        self.assert_tracked(rel)

    def test_file_args_pass_distinct_section_numbers(self):
        # The green control beside the red below: the same file-argument shape, with no duplicate on the tree.
        self.put(SECTIONS + "/s43500-a.py", section_text(43500))
        self.commit_base()
        self.put(SECTIONS + "/s43501-b.py", section_text(43501))
        self.commit_change()
        self.assert_tracked(SECTIONS + "/s43500-a.py", SECTIONS + "/s43501-b.py")
        self.assert_passes(SECTIONS + "/s43501-b.py")

    def test_file_args_still_refuse_two_section_files_on_one_number(self):
        # The check skipped the section read when it was given files, so a duplicate passed as one exited 0.
        self.put(SECTIONS + "/s43500-a.py", section_text(43500))
        self.put(SECTIONS + "/s43500-b.py", section_text(43500))
        self.commit_base()
        self.assert_tracked(SECTIONS + "/s43500-a.py", SECTIONS + "/s43500-b.py")
        rc, out = self.lint(SECTIONS + "/s43500-b.py")
        self.assertEqual(rc, 1, "a duplicate section number passed as a file argument must be refused:\n" + out)
        self.assertEqual(sorted(flagged(out)), [SECTIONS + "/s43500-a.py", SECTIONS + "/s43500-b.py"], out)

    def test_unknown_diff_still_refuses_a_section_duplicate(self):
        # With git UNKNOWN the run returned 0 locally, even after a section fault was printed. CI is unset here.
        self.put(FEEL_DEBT, FEEL_TEXT)
        self.put(SECTIONS + "/s43500-a.py", section_text(43500))
        self.put(SECTIONS + "/s43500-b.py", section_text(43500))
        self.commit_base()
        loose = self.loose_blob(FEEL_DEBT)
        # A packed blob would survive the removal, and git show would not fail, so the case would prove nothing.
        self.assertTrue(os.path.isfile(loose), loose)
        os.remove(loose)
        self.delete(FEEL_DEBT)
        self.commit_change()
        self.assert_tracked(SECTIONS + "/s43500-a.py", SECTIONS + "/s43500-b.py")
        rc, out = self.lint()
        self.assertIn("check_record_slugs: UNKNOWN", out, out)  # scope: the unknown branch is the one under test
        self.assertEqual(rc, 1, "a section duplicate must stay red when the diff is unknown:\n" + out)
        self.assertEqual(sorted(flagged(out)), [SECTIONS + "/s43500-a.py", SECTIONS + "/s43500-b.py"], out)

    def test_section_name_that_reads_and_agrees_with_its_header_passes(self):
        # The green control beside the four name reds below: `s<n>-<slug>.py` whose number is the header's.
        self.add_section_in_change(SECTIONS + "/s43500-x.py", 43500)
        self.assert_passes()

    def test_section_name_with_an_underscore_after_its_number_is_refused(self):
        self.add_section_in_change(SECTIONS + "/s43501_x.py", 43500)
        rc, out = self.lint()
        self.assertEqual(rc, 1, "a section name the check cannot read must be refused, not passed:\n" + out)
        self.assertEqual(flagged(out), [SECTIONS + "/s43501_x.py"], out)

    def test_section_name_with_no_dash_after_its_number_is_refused(self):
        self.add_section_in_change(SECTIONS + "/s43501x.py", 43500)
        rc, out = self.lint()
        self.assertEqual(rc, 1, "a section name the check cannot read must be refused, not passed:\n" + out)
        self.assertEqual(flagged(out), [SECTIONS + "/s43501x.py"], out)

    def test_section_name_without_the_s_prefix_is_refused(self):
        self.add_section_in_change(SECTIONS + "/43501-x.py", 43500)
        rc, out = self.lint()
        self.assertEqual(rc, 1, "a section name the check cannot read must be refused, not passed:\n" + out)
        self.assertEqual(flagged(out), [SECTIONS + "/43501-x.py"], out)

    def test_section_name_with_an_upper_case_s_is_refused(self):
        self.add_section_in_change(SECTIONS + "/S43501-x.py", 43500)
        rc, out = self.lint()
        self.assertEqual(rc, 1, "a section name the check cannot read must be refused, not passed:\n" + out)
        self.assertEqual(flagged(out), [SECTIONS + "/S43501-x.py"], out)


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
