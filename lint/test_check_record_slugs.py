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
FIXED_DEBT = "debts/fixed-debt.md"  # a new debt file with a valid Fix line, beside NEW_DEBT in the same diff
DEBT_NO_FIX = "# New debt\n\nWhat. A gap with no fix named.\n"
PINNED_TODAY = "2026-11-07"  # the date the suite pins: the check reads FIXED_TODAY, so no case reads the clock
KEPT_NOTE = "- kept-note: a gap. Fix: already fixed on main 1a2b3c4\n"  # a bullet with a new-grammar Fix
THIRD_NOTE = "- third-note: a gap. Fix: already fixed on main 1a2b3c4\n"

FAR_PAST_DAYS = 3650  # a Seen this many days old is past any window the decision allows, so it is red whatever the window is
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


def day(offset):
    """The ISO date `offset` days from PINNED_TODAY. A negative offset is in the past."""
    return (datetime.date.fromisoformat(PINNED_TODAY) + datetime.timedelta(days=offset)).isoformat()


def load_module():
    """The module under test, loaded in this process. Importing it runs no check (ImportTests pins that)."""
    spec = importlib.util.spec_from_file_location("record_slugs_under_test", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def module_value(name):
    """The value `name` has in the module under test, or None when the module has none."""
    return getattr(load_module(), name, None)


def write_at(root, rel, text):
    """Write `text` to `rel` under `root`, making its folders. `rel` uses slashes on every platform."""
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def git_at(where, *args):
    """Run git in `where` with a test identity, and return its stdout. Raises when git fails."""
    done = subprocess.run(["git", "-C", where, "-c", "user.name=test", "-c", "user.email=test@example.com", *args],
                          capture_output=True, text=True, check=True)
    return done.stdout.strip()


class RecordSlugsTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(os.path.isfile(MODULE), "module absent: lint/check_record_slugs.py")
        self.tree = tempfile.mkdtemp(prefix="rsl_", dir=RUN_FOLDER)
        self.addCleanup(tracked_tree.rm_tree, self.tree)
        tracked_tree.copy_tracked(self.tree, "lint", "hooks")  # the layout and the check's imports
        shutil.copyfile(MODULE, os.path.join(self.tree, "lint", "check_record_slugs.py"))

    def put(self, rel, text="# Record\n"):
        write_at(self.tree, rel, text)

    def lint(self, *args, cwd=None):
        """Run the copy of the script in the temp tree, from `cwd` (the tree when none is given)."""
        env = dict(os.environ)
        env.pop("CI", None)  # CI turns an unknown diff into red; these cases run locally
        env["FIXED_TODAY"] = PINNED_TODAY  # the check's date comes from here, never from the clock
        cmd = [sys.executable, os.path.join(self.tree, "lint", "check_record_slugs.py"), *args]
        r = subprocess.run(cmd, cwd=cwd or self.tree, env=env, capture_output=True, text=True,
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
        # One edit drops a Fix and another adds one. The count stays at one, so the branch passes. The edited line keeps
        # its Seen field: a base line with a Seen field keeps one (lane ruling 1, 2026-11-07 15:58 CST).
        self.put(DEBT_NOTES, NOTES_HEAD + OLD_NOTE + KEPT_NOTE)
        self.commit_base()
        self.put(DEBT_NOTES, NOTES_HEAD + "- old-note: an old gap. Fix: already fixed on main 1a2b3c4\n"
                 + "- kept-note: a gap, its Fix removed. Seen: %s x1.\n" % PINNED_TODAY)
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

    # Sightings (decision notes-sightings-expiry). A notes line the branch adds carries `Seen: YYYY-MM-DD xN` before its
    # Fix field: N is 1 or more, and the date is today or earlier and no older than SEEN_EXPIRY_DAYS. N of 2 or more
    # fails, because the note is a debt now. An edit may not lower the count below the merge base. Old lines never turn red.

    def window(self):
        days = module_value("SEEN_EXPIRY_DAYS")
        self.assertIsInstance(days, int, "lint/check_record_slugs.py has no SEEN_EXPIRY_DAYS, so the Seen window is not built")
        return days

    def cap(self):
        days = module_value("UNTIL_CAP_DAYS")
        self.assertIsInstance(days, int, "lint/check_record_slugs.py has no UNTIL_CAP_DAYS")
        return days

    def fail_line(self, out, needle):
        """The first FAIL line of the check that names `needle`, or '' when none does."""
        return next((line for line in out.splitlines()
                     if line.startswith("check_record_slugs: FAIL:") and needle in line), "")

    def test_added_note_without_seen_is_red(self):
        self.add_note("- unseen-note: a gap. Fix: none — owner decides. Until: %s\n" % day(6))
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertIn("Seen", self.fail_line(out, "unseen-note"), out)

    def test_added_note_with_a_valid_seen_passes(self):
        # The control for the case above, in the step form and the none form. Seen sits before the Fix field.
        self.put(DEBT_NOTES, NOTES_HEAD)
        self.commit_base()
        self.roadmap("alpha-beta")
        self.put(DEBT_NOTES, NOTES_HEAD
                 + "- seen-step: a gap. Seen: %s x1. Fix: step:alpha-beta\n" % day(0)
                 + "- seen-none: a gap. Seen: %s x1. Fix: none — owner decides. Until: %s\n" % (day(0), day(6)))
        self.commit_change()
        self.assert_passes()

    def test_seen_older_than_the_window_is_red(self):
        old = day(-FAR_PAST_DAYS)
        self.add_note("- stale-note: a gap. Seen: %s x1. Fix: none — owner decides. Until: %s\n" % (old, day(6)))
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertTrue(self.fail_line(out, "stale-note"), out)

    def test_seen_in_the_future_is_red(self):
        self.add_note("- early-note: a gap. Seen: %s x1. Fix: none — owner decides. Until: %s\n" % (day(1), day(6)))
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertTrue(self.fail_line(out, "early-note"), out)

    def test_seen_at_the_window_edge_passes(self):
        # "No more than SEEN_EXPIRY_DAYS old": the edge is still valid.
        self.add_note("- edge-note: a gap. Seen: %s x1. Fix: none — owner decides. Until: %s\n"
                      % (day(-self.window()), day(6)))
        self.assert_passes()

    def test_malformed_seen_on_an_added_note_is_red(self):
        # Four lines, each with one malformed field: no count, a count of 0, a date that is not one, and a word for a date.
        fields = {
            "no-count-note": "Seen: %s." % day(0),
            "zero-count-note": "Seen: %s x0." % day(0),
            "bad-date-note": "Seen: 2026-13-45 x1.",
            "word-date-note": "Seen: soon x1.",
        }
        self.add_note("".join("- %s: a gap. %s Fix: none — owner decides. Until: %s\n" % (slug, field, day(6))
                              for slug, field in fields.items()))
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        for slug in fields:
            with self.subTest(slug=slug):
                self.assertTrue(self.fail_line(out, slug), out)

    def test_last_seen_on_a_line_counts(self):
        # The first Seen is valid and the last is far past the window, so the line is red.
        old = day(-FAR_PAST_DAYS)
        self.add_note("- two-seen-note: a gap. Seen: %s x1. Seen: %s x1. Fix: none — owner decides. Until: %s\n"
                      % (day(0), old, day(6)))
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertTrue(self.fail_line(out, "two-seen-note"), out)

    def test_added_note_at_two_sightings_is_red_and_says_file_it_as_a_debt(self):
        self.add_note("- twice-note: a gap. Seen: %s x2. Fix: none — owner decides. Until: %s\n" % (day(0), day(6)))
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertIn("debt", self.fail_line(out, "twice-note"), out)

    def test_repeat_sighting_that_raises_a_note_to_two_is_red(self):
        # The base holds the note at one sighting. The branch raises it to two: a second sighting makes it a debt.
        self.put(DEBT_NOTES, NOTES_HEAD + "- repeat-note: a gap. Seen: %s x1. Fix: none — owner decides. Until: %s\n"
                 % (day(-1), day(6)))
        self.commit_base()
        self.put(DEBT_NOTES, NOTES_HEAD + "- repeat-note: a gap. Seen: %s x2. Fix: none — owner decides. Until: %s\n"
                 % (day(0), day(6)))
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertIn("debt", self.fail_line(out, "repeat-note"), out)

    def test_edit_that_drops_the_count_below_the_base_is_red(self):
        self.put(DEBT_NOTES, NOTES_HEAD + "- counted-note: a gap. Seen: %s x3. Fix: none — owner decides. Until: %s\n"
                 % (day(-1), day(6)))
        self.commit_base()
        self.put(DEBT_NOTES, NOTES_HEAD + "- counted-note: a gap. Seen: %s x1. Fix: none — owner decides. Until: %s\n"
                 % (day(0), day(6)))
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertTrue(self.fail_line(out, "counted-note"), out)

    def test_edit_that_keeps_the_count_and_moves_the_date_passes(self):
        self.put(DEBT_NOTES, NOTES_HEAD + "- kept-count: a gap. Seen: %s x1. Fix: none — owner decides. Until: %s\n"
                 % (day(-1), day(6)))
        self.commit_base()
        self.put(DEBT_NOTES, NOTES_HEAD + "- kept-count: a gap. Seen: %s x1. Fix: none — owner decides. Until: %s\n"
                 % (day(0), day(6)))
        self.commit_change()
        self.assert_passes()

    def test_old_note_without_seen_passes_when_edited(self):
        # Old lines never turn red: an edit that adds no Seen field to an old line is judged on its Until only.
        self.put(DEBT_NOTES, NOTES_HEAD + "- old-bare: an old gap. Fix: none — owner decides. Until: %s\n" % day(6))
        self.commit_base()
        self.put(DEBT_NOTES, NOTES_HEAD + "- old-bare: an old gap, reworded. Fix: none — owner decides. Until: %s\n"
                 % day(6))
        self.commit_change()
        self.assert_passes()

    # Pins: a sighting is an edit, so it carries the Until rule with it. Each case here is red or green on the base
    # already, because the Until rule judges every edited line. The cases stop a Seen change from skipping that rule.

    def test_raising_seen_on_an_old_none_note_with_a_past_until_is_red(self):
        self.put(DEBT_NOTES, NOTES_HEAD + "- old-none: a gap. Fix: none — owner decides. Until: %s\n" % day(-1))
        self.commit_base()
        self.put(DEBT_NOTES, NOTES_HEAD + "- old-none: a gap. Seen: %s x1. Fix: none — owner decides. Until: %s\n"
                 % (day(0), day(-1)))
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertTrue(self.fail_line(out, "old-none"), out)

    def test_raising_seen_on_an_old_none_note_with_a_fresh_until_passes(self):
        # The base line's Until is past. The sighting refreshes it, so the edit passes.
        self.put(DEBT_NOTES, NOTES_HEAD + "- old-none: a gap. Fix: none — owner decides. Until: %s\n" % day(-1))
        self.commit_base()
        self.put(DEBT_NOTES, NOTES_HEAD + "- old-none: a gap. Seen: %s x1. Fix: none — owner decides. Until: %s\n"
                 % (day(0), day(6)))
        self.commit_change()
        self.assert_passes()

    def test_raising_seen_on_a_none_note_past_the_until_cap_is_red(self):
        self.put(DEBT_NOTES, NOTES_HEAD + "- old-none: a gap. Fix: none — owner decides. Until: %s\n" % day(6))
        self.commit_base()
        self.put(DEBT_NOTES, NOTES_HEAD + "- old-none: a gap. Seen: %s x1. Fix: none — owner decides. Until: %s\n"
                 % (day(0), day(self.cap() + 1)))
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertTrue(self.fail_line(out, "old-none"), out)

    def test_seen_before_the_fix_leaves_parse_fix_and_until_of_unchanged(self):
        # Pinned invariant for the step form and the none form: a Seen field before Fix moves neither reading.
        check = load_module()
        cases = [
            ("- step-note: a gap. Fix: step:alpha-beta", ("step", "alpha-beta"), None),
            ("- none-note: a gap. Fix: none — owner decides. Until: %s" % day(6), ("none", "owner decides"),
             datetime.date.fromisoformat(day(6))),
        ]
        for line, fix, until in cases:
            seen = line.replace(". Fix:", ". Seen: %s x1. Fix:" % day(0), 1)
            with self.subTest(line=line):
                self.assertNotEqual(seen, line, "the fixture line has no Fix field to put Seen before")
                self.assertEqual(check.parse_fix(seen), fix, seen)
                self.assertEqual(check.parse_fix(seen), check.parse_fix(line), seen)
                self.assertEqual(check.until_of(seen), until, seen)

    # Debt files: a Seen line at column one, or after one leading "- ", must be valid when it is present.

    def test_debt_file_with_a_malformed_seen_line_is_red(self):
        fix = "\nFix: none — owner decides\n"
        bad = {
            "debts/seen-no-count.md": "Seen: %s\n" % day(0),
            "debts/seen-zero.md": "- Seen: %s x0\n" % day(0),
            "debts/seen-bad-date.md": "Seen: 2026-13-45 x2\n",
            "debts/seen-word.md": "- Seen: often x2\n",
        }
        self.put(DEBT_NOTES, NOTES_HEAD)
        self.commit_base()
        for rel, line in bad.items():
            self.put(rel, "# Debt\n\nWhat. A gap with a fix named.\n" + line + fix)
        self.put(FIXED_DEBT, FIXED_DEBT_TEXT)  # the control: a valid Fix and no Seen, in the same diff
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        for rel in bad:
            with self.subTest(debt=rel):
                self.assertTrue(self.failed_about(out, rel), out)
        self.assertFalse(self.failed_about(out, FIXED_DEBT), out)

    def test_an_edit_that_drops_a_seen_field_is_red(self):
        # Decision notes-sightings-expiry (lane ruling 2026-11-07 15:58 CST): a note whose base line had a Seen field keeps
        # one. An edit that drops it is red, whatever the date was.
        self.put(DEBT_NOTES, NOTES_HEAD + "- kept-note: a gap. Seen: %s x1. Fix: none — owner decides. Until: 2026-11-20\n"
                 % day(-1))
        self.commit_base()
        self.put(DEBT_NOTES, NOTES_HEAD + "- kept-note: a gap. Fix: none — owner decides. Until: 2026-11-20\n")
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertIn("kept-note", out, out)

    def test_debt_file_with_a_seen_date_in_the_future_is_red(self):
        self.put(DEBT_NOTES, NOTES_HEAD)
        self.commit_base()
        self.put(NEW_DEBT, "# New debt\n\nWhat. A gap with a fix named.\n\nSeen: %s x2\nFix: none — owner decides\n"
                 % day(1))
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertIn("in the future", out, out)
        self.assertTrue(self.failed_about(out, NEW_DEBT), out)

    def test_debt_file_with_an_old_seen_date_passes(self):  # a debt's Seen has no age limit, unlike a note's
        self.put(DEBT_NOTES, NOTES_HEAD)
        self.commit_base()
        self.put(NEW_DEBT, "# New debt\n\nWhat. A gap with a fix named.\n\nSeen: %s x2\nFix: none — owner decides\n"
                 % day(-FAR_PAST_DAYS))
        self.commit_change()
        self.assert_passes()

    def test_debt_file_with_a_valid_seen_line_passes(self):
        self.put(DEBT_NOTES, NOTES_HEAD)
        self.commit_base()
        self.put(NEW_DEBT, "# New debt\n\nWhat. A gap with a fix named.\n\nSeen: %s x2\nFix: none — owner decides\n"
                 % day(0))
        self.put("debts/bullet-seen.md", "# Bullet\n\nWhat. A gap.\n\n- Seen: %s x1\n- Fix: none — owner decides\n"
                 % day(-2))
        self.commit_change()
        self.assert_passes()

    def test_lone_quote_and_comment_opener_do_not_hide_the_seen_field(self):
        # The apostrophe and the comment openers are text. The first line passes; the second is red for its count.
        self.put(DEBT_NOTES, NOTES_HEAD)
        self.commit_base()
        self.put(DEBT_NOTES, NOTES_HEAD
                 + "- quote-seen: Don't drop the lock (see /* the old block */). Seen: %s x1. "
                   "Fix: none — owner decides. Until: %s\n" % (day(0), day(6))
                 + "- quote-twice: Don't // drop it, say \"again\". Seen: %s x2. "
                   "Fix: none — owner decides. Until: %s\n" % (day(0), day(6)))
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertIn("debt", self.fail_line(out, "quote-twice"), out)
        self.assertFalse(self.failed_about(out, "quote-seen"), out)

    # --next-debt: the highest-Seen debt slug. Ties go to the oldest date, then the slug. A debt with no Seen line is x1.

    def put_debt(self, slug, seen_line=None):
        body = "# %s\n\nWhat. A gap with a fix named.\n\nFix: none — owner decides\n" % slug
        if seen_line:
            body += seen_line + "\n"
        self.put("debts/%s.md" % slug, body)

    def assert_next_debt(self, expected):
        # --next-debt reads the repo of the current directory, so the tree must be one. It reads the debt folders from
        # the working tree, so no commit is needed.
        if not os.path.isdir(os.path.join(self.tree, ".git")):
            self.git("init", "-q")
        rc, out = self.lint("--next-debt")
        self.assertEqual(rc, 0, "--next-debt did not exit 0 (not built?): %s" % out)
        self.assertEqual(out.strip(), expected, out)

    def test_next_debt_names_the_highest_count(self):
        self.put_debt("alpha", "Seen: %s x2" % day(-30))
        self.put_debt("beta", "- Seen: %s x5" % day(-1))  # a bullet form, and the highest count
        self.put_debt("gamma", "Seen: %s x3" % day(-60))
        self.assert_next_debt("beta")

    def test_next_debt_breaks_a_count_tie_by_the_oldest_date(self):
        self.put_debt("aaa-later", "Seen: %s x3" % day(-1))  # the alphabet would pick this one
        self.put_debt("zzz-earlier", "Seen: %s x3" % day(-20))
        self.assert_next_debt("zzz-earlier")

    def test_next_debt_breaks_a_date_tie_by_the_slug(self):
        self.put_debt("zeta", "Seen: %s x3" % day(-5))
        self.put_debt("alpha", "Seen: %s x3" % day(-5))
        self.assert_next_debt("alpha")

    def test_next_debt_counts_a_debt_with_no_seen_line_as_one(self):
        self.put_debt("quiet")
        self.put_debt("twice", "Seen: %s x2" % day(-1))
        self.assert_next_debt("twice")  # x2 beats the x1 that a debt with no Seen line counts as
        self.delete("debts/twice.md")
        self.assert_next_debt("quiet")  # alone, a debt with no Seen line is still the one to fix

    def test_next_debt_ignores_the_notes_file_and_the_readme(self):
        self.put(DEBT_NOTES, NOTES_HEAD + "- loud-note: a gap. Seen: %s x9. Fix: step:alpha-beta\n" % day(-1))
        self.put(DEBT_README, "# Debts\n\nSeen: %s x9\n" % day(-1))
        self.put_debt("small", "Seen: %s x1" % day(-1))
        self.assert_next_debt("small")

    def test_next_debt_ranks_an_undated_debt_after_a_dated_one_in_a_count_tie(self):
        self.put_debt("aaa-undated")  # no Seen line: x1 with no date, and the alphabet would pick it
        self.put_debt("zzz-dated", "Seen: %s x1" % day(-1))
        self.assert_next_debt("zzz-dated")

    # --debt-flow START END: the debts opened and closed between two refs. The notes file and the README are not debts.

    def test_debt_flow_names_the_debts_opened_and_closed_and_nothing_else(self):
        self.put("debts/retired-debt.md", DEBT_NO_FIX)
        self.put("debts/kept-debt.md", DEBT_NO_FIX)
        self.put(DEBT_NOTES, NOTES_HEAD)
        self.put(DEBT_README, "# Debts\n\nOne debt per file.\n")
        self.commit_base()
        self.git("commit", "--allow-empty", "-q", "-m", "start")  # START is this empty commit: the base's debts came before it
        start = self.head_sha()
        self.put("debts/fresh-debt.md", FIXED_DEBT_TEXT)  # opened
        self.delete("debts/retired-debt.md")  # closed
        self.put("debts/kept-debt.md", DEBT_NO_FIX + "\nMore detail, the same debt.\n")  # edited, neither opened nor closed
        self.put(DEBT_NOTES, NOTES_HEAD + "- new-note-line: a gap. Seen: %s x1. Fix: step:alpha-beta\n" % day(0))
        self.put(DEBT_README, "# Debts\n\nOne debt per file, as before.\n")
        self.commit_change()
        rc, out = self.lint("--debt-flow", start, "HEAD")
        self.assertEqual(rc, 0, "--debt-flow did not exit 0 (not built?): %s" % out)
        self.assertIn("fresh-debt", out, out)
        self.assertIn("retired-debt", out, out)
        self.assertNotIn("kept-debt", out, out)
        self.assertNotIn("new-note-line", out, out)
        self.assertNotIn("README.md", out, out)
        self.assertNotIn("notes.md", out, out)

    def test_debt_flow_counts_a_debt_added_in_the_start_commit(self):
        # Decision notes-sightings-expiry (lane ruling 2026-11-07 15:58 CST): the window includes the START commit's own
        # additions, so a debt that START adds and the end still holds is opened.
        self.put("debts/early-debt.md", DEBT_NO_FIX)  # added in START itself
        self.put(DEBT_NOTES, NOTES_HEAD)
        self.commit_base()
        start = self.head_sha()
        self.put("debts/later-debt.md", FIXED_DEBT_TEXT)
        self.commit_change()
        rc, out = self.lint("--debt-flow", start, "HEAD")
        self.assertEqual(rc, 0, "--debt-flow did not exit 0 (not built?): %s" % out)
        lines = out.splitlines()
        self.assertEqual(lines[:1], ["debts opened 2, closed 0"], out)
        self.assertEqual(sorted(lines[1:]), ["+ early-debt", "+ later-debt"], out)

    def test_debt_flow_prints_the_count_line_then_one_plus_or_minus_line_per_debt(self):
        self.put("debts/closed-one.md", DEBT_NO_FIX)
        self.put("debts/kept.md", DEBT_NO_FIX)  # neither opened nor closed: it must not appear
        self.put(DEBT_NOTES, NOTES_HEAD)
        self.commit_base()
        self.git("commit", "--allow-empty", "-q", "-m", "start")  # START is this empty commit: the base's debts came before it
        start = self.head_sha()
        self.put("debts/opened-b.md", FIXED_DEBT_TEXT)
        self.put("debts/opened-a.md", FIXED_DEBT_TEXT)
        self.delete("debts/closed-one.md")
        self.commit_change()
        rc, out = self.lint("--debt-flow", start, "HEAD")
        self.assertEqual(rc, 0, "--debt-flow did not exit 0 (not built?): %s" % out)
        lines = out.splitlines()
        self.assertEqual(lines[:1], ["debts opened 2, closed 1"], out)
        self.assertEqual(sorted(lines[1:]), ["+ opened-a", "+ opened-b", "- closed-one"], out)

    def test_next_debt_and_debt_flow_read_the_repo_of_the_current_directory(self):
        # Decision notes-sightings-expiry: both read the repo of the current directory, never the repo that holds the
        # script. The script copy sits in a folder that is no repo, and it holds a debt that would win if it were read.
        self.put_debt("script-debt", "Seen: %s x9" % day(-1))
        away = tempfile.mkdtemp(prefix="cwd_", dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, away, True)
        git_at(away, "init", "-q")
        write_at(away, "debts/cwd-debt.md", "# Debt\n\nWhat. A gap with a fix named.\n\nSeen: %s x3\n"
                 "Fix: none — owner decides\n" % day(-1))
        write_at(away, "debts/retired-cwd.md", FIXED_DEBT_TEXT)
        git_at(away, "add", "-A")
        git_at(away, "commit", "-q", "-m", "base")
        git_at(away, "commit", "-q", "--allow-empty", "-m", "start")  # START is this empty commit: the base came before it
        start = git_at(away, "rev-parse", "HEAD")
        write_at(away, "debts/fresh-cwd.md", FIXED_DEBT_TEXT)
        os.remove(os.path.join(away, "debts", "retired-cwd.md"))
        git_at(away, "add", "-A")
        git_at(away, "commit", "-q", "-m", "change")
        with self.subTest(command="--next-debt"):
            rc, out = self.lint("--next-debt", cwd=away)
            self.assertEqual(rc, 0, "--next-debt did not exit 0 in the current directory's repo: %s" % out)
            self.assertEqual(out.strip(), "cwd-debt", "--next-debt read a repo other than the current directory's: %s"
                             % out)
        with self.subTest(command="--debt-flow"):
            rc, out = self.lint("--debt-flow", start, "HEAD", cwd=away)
            self.assertEqual(rc, 0, "--debt-flow did not exit 0 in the current directory's repo: %s" % out)
            self.assertEqual(out.splitlines(), ["debts opened 1, closed 1", "+ fresh-cwd", "- retired-cwd"],
                             "--debt-flow read a repo other than the current directory's: %s" % out)


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
