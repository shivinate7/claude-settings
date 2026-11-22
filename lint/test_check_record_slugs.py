#!/usr/bin/env python3
"""Cases for lint/check_record_slugs.py. Standard library only.

    python3 lint/test_check_record_slugs.py

A record file that a change adds must have a slug of 32 characters or fewer. The check reads
decisions/ and debts/ from the diff, or the files it is given.

A section file under tests/guard/ has a `# section <n>` header on its first line. Its name is `s<n>-<slug>.py`,
and a name that does not read so is refused. Its number must be its name's number, and no other section file may
hold it. The tree is read, not only the diff, and file arguments do not skip that read. A clash's fault names each
file on the number and the next free number, and the ready run (merge.readyChecks) reads the step that finds it.

Each case builds a temp tree: a copy of the module, and the records it checks. It runs the real
script from that tree. The diff cases also make a temp git repo and set refs/remotes/origin/main,
the base the script diffs against. RECORD_SLUGS_UNDER_TEST overrides the module path.
"""
import ast
import contextlib
import datetime
import importlib.util
import io
import json
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
import _guard_sections  # noqa: E402  the one home of the section header read and the faults (lint/_guard_sections.py)
MODULE =os.environ.get("RECORD_SLUGS_UNDER_TEST") or os.path.join(HERE, "check_record_slugs.py")
RUNNER = os.path.join(HERE, "..", "hooks", "test_guard.py")  # its SECTION_DIR names the section folder the check reads
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import tracked_tree  # noqa: E402  copies what git lists, so no fixture lists files (testing/tracked_tree.py)
STAMP = os.path.join(HERE, "..", ".github", "stamp.json")  # merge.readyChecks lists the steps the ready run reads

OK ="a" * 32 + ".md"  # a slug of 32 characters passes
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
# One file per note: the frozen notes file takes deletes only, and each note is a file under the note folder.
REPO = os.path.dirname(HERE)
OLD_NOTES = "docs/debts/notes.md"  # the frozen notes file
NOTE_DIR = "docs/notes"
NOTE = NOTE_DIR + "/%s.md"  # a note file, named by its slug
SLUG_MAX = "wheel-speed-cap-" + "abcdefghijklmnop"  # 32 characters: the longest slug a note file may have
SLUG_LONG = SLUG_MAX + "q"  # 33 characters
SLUG_LINE = re.compile(r"^- [a-z0-9-]+: ")  # a note line in the `- slug: text` form
NOTE_TEXT = ("- %s: the spin rate is capped at twelve degrees per frame (hooks/guard.py) "
             "Seen: 2026-11-17 x1\n")  # a valid note: one line, with a Seen field the check accepts
NEW_LINE = ("- wheel-speed-probe: a line added to the frozen file (hooks/guard.py) Fix: none — rare and "
            "harmless. Until: 2026-11-30")
# Real lines of the notes file as they stand: one with no `- slug:` form, one with a lone quote and a backslash.
NO_SLUG_LINE = ("- AskUserQuestion gain/loss rule may refuse terse real choices: check it on real questions. "
                "Decision: question-reviewer-agent-hook. Fix: none — rare and harmless. Until: 2026-11-19")
ANSI_LINE = ("- ansi-c-escape-not-decoded: escapes inside $'...' such as \\x2f stay text, so a protected path spelled "
             "with escapes passes frozen and cap checks (hooks/guard_frozen.py) Fix: none — rare and harmless. "
             "Until: 2026-11-24")
MISMATCH_TEXT = "- beta-note: the spin rate is capped at twelve degrees per frame (hooks/guard.py)\n"
README_TEXT = "# Notes\n\nOne note per file: `<slug>.md`, holding one line `- <slug>: <text>`.\n"
EDIT_OLD = "- edited-note: the first wording of the note (hooks/guard.py)\n"
EDIT_NEW = "- edited-note: the second wording of the note (hooks/guard.py)\n"

SECTIONS = "tests/guard"  # the section folder, as hooks/test_guard.py's SECTION_DIR names it
PINNED_TODAY = "2026-11-18"  # the clock every case pins: the check reads FIXED_TODAY, so no case reads the real date
CENTRAL_NOON = "2000-01-17T12:00:00-06:00"  # a noon on a fixed Central day: the check reads it, not the machine's
MACHINE_ZONE = "UTC-14"  # a POSIX zone far from Central: the machine's date must not enter a Central-dated verdict
# The text of docs/notes/ps-scriptblock-path-refused.md, copied as the fixture: a real note's length and form.
REAL_NOTE_TEXT = ("the check still refuses `@{N='x'; E={ ./x.ps1 }}`, since the scriptblock lookahead covers only a "
                  "letter after `{ ` while the trailing class also takes `.` and `/` (hooks/question_form.py "
                  "PS_BASH_FORMS, its NAME= alternative). Decision: act-in-place")
# That note's line as its file holds it on main, with its Seen field. Fixed text: a note added later cannot change it.
REAL_NOTE_LINE = "- ps-scriptblock-path-refused: %s Seen: 2026-11-17 x1\n" % REAL_NOTE_TEXT
RENAME_FROM = "alpha-note"  # a rename pair of one length, so git reads the rename: the slug changes, the text does not
RENAME_TO = "bravo-note"


def section_text(n, body=""):
    """A section file: its first line is the `# section <n>` header that test_guard.py reads."""
    return "# section %d\n%s" % (n, body)


def day(offset):
    """The ISO date `offset` days from PINNED_TODAY. A negative offset is in the past."""
    return (datetime.date.fromisoformat(PINNED_TODAY) + datetime.timedelta(days=offset)).isoformat()


def seen(offset, count):
    """A Seen field: the date `offset` days from PINNED_TODAY, and the sighting count."""
    return "Seen: %s x%d" % (day(offset), count)


def note_line(slug, field=None):
    """A note file's one line, `- <slug>: <text>`, with the Seen field at its end when one is given."""
    return "- %s: %s%s\n" % (slug, REAL_NOTE_TEXT, " " + field if field else "")


def debt_body(slug, seen_line=None):
    """A debt file: a title, a body, and the Seen line when one is given."""
    return "# %s\n\nWhat. A gap with a fix named.\n%s" % (slug, seen_line + "\n" if seen_line else "")


def clean_env(**extra):
    """The environment a check run gets: CI and git's repo variables stripped, the clock pinned, `extra` added.
    A value of None in `extra` removes that variable."""
    env = dict(os.environ)
    for key in ("CI", "GIT_DIR", "GIT_WORK_TREE"):  # CI turns an unknown diff red; the repo variables pick the repo
        env.pop(key, None)
    env["FIXED_TODAY"] = PINNED_TODAY
    for key, value in extra.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    return env


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


AGENT_RULES = "AGENT_FORM_RULES"  # the one list of agent-facing record-form rules, in check_record_slugs.py
NOTE_FORM = "- <slug>: <text>"  # the form a note line takes (decision notes-merge-union)


def note_rule(module_path):
    """(the note rule as a refusal prints it, None), read from the module under test, or (None, problem). The rule is
    the list's entry that holds the note form, with the note folder and the old notes file filled in."""
    try:
        spec = importlib.util.spec_from_file_location("check_record_slugs_under_test", module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        rules = getattr(module, AGENT_RULES, None)
    except Exception as exc:  # a module that does not load is a red case, never a crash
        return None, "the module under test does not load: %s" % exc
    if rules is None:
        return None, "check_record_slugs has no %s list, the one home of the agent-facing rules" % AGENT_RULES
    for rule in rules:
        if "{folder}" in rule and NOTE_FORM in rule:
            return rule.replace("{folder}", NOTE_DIR + "/").replace("{old}", OLD_NOTES), None
    return None, "no entry of %s holds the note form with {folder}" % AGENT_RULES


class RecordSlugsTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(os.path.isfile(MODULE), "module absent: lint/check_record_slugs.py")
        self.tree = tempfile.mkdtemp(prefix="rsl_", dir=RUN_FOLDER)
        self.addCleanup(tracked_tree.rm_tree, self.tree)
        tracked_tree.copy_tracked(self.tree, "lint", "hooks")  # the layout and the check's imports
        shutil.copyfile(MODULE, os.path.join(self.tree, "lint", "check_record_slugs.py"))
        # tracked_tree leaves out test_ files, and the section check finds the folder through the runner, so copy it.
        shutil.copyfile(RUNNER, os.path.join(self.tree, "hooks", "test_guard.py"))

    def put(self, rel, text="# Record\n"):
        path = os.path.join(self.tree, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

    def run_check(self, cwd, *args, **env_extra):
        """The check run on the command line from `cwd`, with clean_env(**env_extra). Returns (exit code, output)."""
        cmd = [sys.executable, os.path.join(self.tree, "lint", "check_record_slugs.py"), *args]
        r = subprocess.run(cmd, cwd=cwd, env=clean_env(**env_extra), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        return r.returncode, r.stdout + r.stderr

    def lint(self, *args):
        return self.run_check(self.tree, *args)

    def fail_line(self, out, needle):
        """The first FAIL line of the check that names `needle`, or '' when none does."""
        return next((line for line in out.splitlines()
                     if line.startswith("check_record_slugs: FAIL:") and needle in line), "")

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

    # One file per note. The frozen notes file takes deletes only; a note file under NOTE_DIR holds one line.

    def roll_out(self):
        self.put(".claude/layout-extras.json", '{"rolled-out": true, "kinds": {}}\n')

    def frozen_base(self):
        """Rolls the tree out and puts the checkout's own notes file in it as the base. Returns its lines."""
        self.roll_out()
        with open(os.path.join(REPO, *OLD_NOTES.split("/")), encoding="utf-8", newline="") as f:
            lines = f.read().splitlines()
        self.assertTrue(any(SLUG_LINE.match(line) for line in lines), "the notes file holds no slug line to pick")
        self.put(OLD_NOTES, "\n".join(lines) + "\n")
        return lines

    def git_out(self, *args):
        return subprocess.run(["git", "-C", self.tree, *args], capture_output=True, text=True, check=True).stdout

    def remedy_names_note_folder(self, out):
        """A refusal names the note folder, and no line of its output names the frozen notes file: the remedy is the
        note form only."""
        self.assertTrue(any(NOTE_DIR + "/" in line for line in out.splitlines()), out)
        self.assertNotIn(OLD_NOTES, out, "a refusal names the frozen notes file")

    def test_added_line_in_the_frozen_notes_file_is_refused(self):
        lines = self.frozen_base()
        self.commit_base()
        self.put(OLD_NOTES, "\n".join(lines + [NEW_LINE]) + "\n")
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.remedy_names_note_folder(out)

    def test_refusal_prints_the_note_rule_the_list_holds(self):
        """The refusal prints the note rule from the one list in check_record_slugs, so the brief and the check share it."""
        rule, problem = note_rule(MODULE)
        self.assertIsNone(problem, problem)
        lines = self.frozen_base()
        self.commit_base()
        self.put(OLD_NOTES, "\n".join(lines + [NEW_LINE]) + "\n")
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertIn(rule, out, out)

    def test_deleted_line_in_the_frozen_notes_file_passes_beside_a_bad_note(self):
        lines = self.frozen_base()
        self.commit_base()
        gone = [line for line in lines if SLUG_LINE.match(line)][0]
        at = lines.index(gone)
        self.put(OLD_NOTES, "\n".join(lines[:at] + lines[at + 1:]) + "\n")
        self.put(NOTE % "no-slug-line", NO_SLUG_LINE + "\n")
        self.commit_change()
        numstat = self.git_out("diff", "--numstat", "origin/main", "HEAD", "--", OLD_NOTES)
        self.assertTrue(numstat.strip(), "the frozen file is not in the diff")
        self.assertEqual(numstat.split()[:2], ["0", "1"], numstat)  # one deleted line, nothing added
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertEqual(flagged(out), [NOTE % "no-slug-line"], out)

    def test_in_place_edit_of_a_frozen_note_line_is_refused(self):
        lines = self.frozen_base()
        self.commit_base()
        dated = [line for line in lines if SLUG_LINE.match(line) and "Until: " in line]
        self.assertTrue(dated, "the notes file holds no dated note line to edit")
        edited = re.sub(r"Until: \S+$", "Until: 2030-01-01", dated[0])
        self.assertNotEqual(edited, dated[0], "the picked line has no date to change")
        at = lines.index(dated[0])
        self.put(OLD_NOTES, "\n".join(lines[:at] + [edited] + lines[at + 1:]) + "\n")
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.remedy_names_note_folder(out)

    def test_two_old_lines_swapped_pass_beside_a_bad_note(self):
        # Each added line's text is in the base already, so the swap passes; the bad note is the one named.
        lines = self.frozen_base()
        self.commit_base()
        slugged = [line for line in lines if SLUG_LINE.match(line)]
        self.assertGreaterEqual(len(slugged), 2, "the notes file holds two slug lines to swap")
        a, b = lines.index(slugged[0]), lines.index(slugged[1])
        swapped = list(lines)
        swapped[a], swapped[b] = swapped[b], swapped[a]
        self.put(OLD_NOTES, "\n".join(swapped) + "\n")
        self.put(NOTE % "no-slug-line", NO_SLUG_LINE + "\n")
        self.commit_change()
        added = self.git_out("diff", "--numstat", "origin/main", "HEAD", "--", OLD_NOTES).split()[:1]
        self.assertTrue(added and int(added[0]) > 0, "the swap adds no line: nothing is judged")
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertEqual(flagged(out), [NOTE % "no-slug-line"], out)

    def test_note_file_name_over_32_characters_is_refused_beside_a_32_character_one(self):
        self.roll_out()
        self.commit_base()
        self.put(NOTE % SLUG_LONG, NOTE_TEXT % SLUG_LONG)
        self.put(NOTE % SLUG_MAX, NOTE_TEXT % SLUG_MAX)
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertEqual(flagged(out), [NOTE % SLUG_LONG], out)

    def test_refused_long_note_name_prints_the_note_form_rule_and_not_the_old_file(self):
        self.roll_out()
        self.commit_base()
        self.put(NOTE % SLUG_LONG, NOTE_TEXT % SLUG_LONG)
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        rules = [line for line in out.splitlines() if line.startswith("check_record_slugs: note rule: ")]
        self.assertTrue(any(NOTE_DIR + "/" in line and NOTE_FORM in line for line in rules), out)
        self.remedy_names_note_folder(out)

    def test_note_file_without_a_slug_line_is_refused(self):
        self.roll_out()
        self.commit_base()
        self.put(NOTE % "no-slug-line", NO_SLUG_LINE + "\n")
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertEqual(flagged(out), [NOTE % "no-slug-line"], out)

    def test_note_file_whose_slug_differs_from_its_name_is_refused(self):
        self.roll_out()
        self.commit_base()
        self.put(NOTE % "alpha-note", MISMATCH_TEXT)
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertEqual(flagged(out), [NOTE % "alpha-note"], out)

    def test_readme_in_the_notes_folder_passes_beside_a_bad_note(self):
        self.roll_out()
        self.commit_base()
        self.put(NOTE_DIR + "/README.md", README_TEXT)
        self.put(NOTE % "alpha-note", MISMATCH_TEXT)
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertEqual(flagged(out), [NOTE % "alpha-note"], out)

    def test_added_valid_note_file_passes_beside_a_bad_note(self):
        self.roll_out()
        self.commit_base()
        self.put(NOTE % "ansi-c-escape-not-decoded", ANSI_LINE + " " + seen(-1, 1) + "\n")
        self.put(NOTE % "alpha-note", MISMATCH_TEXT)
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertEqual(flagged(out), [NOTE % "alpha-note"], out)

    def test_deleted_and_edited_note_files_pass_beside_a_bad_note(self):
        self.roll_out()
        self.put(NOTE % "gone-note", NOTE_TEXT % "gone-note")
        self.put(NOTE % "edited-note", EDIT_OLD)
        self.commit_base()
        self.delete(NOTE % "gone-note")
        self.put(NOTE % "edited-note", EDIT_NEW)
        self.put(NOTE % "no-slug-line", NO_SLUG_LINE + "\n")
        self.commit_change()
        statuses = self.git_out("diff", "--name-status", "origin/main", "HEAD").splitlines()
        self.assertIn("D\t" + NOTE % "gone-note", statuses, statuses)  # scope: the delete is in the diff
        self.assertIn("M\t" + NOTE % "edited-note", statuses, statuses)  # scope: the edit is in the diff
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertEqual(flagged(out), [NOTE % "no-slug-line"], out)

    # The frozen file's line test counts copies, splits on "\n" only, and reads every edited note file.
    # Separators and BOMs are escapes in this source: a raw control character here would read as a line break.

    def test_second_copy_of_a_frozen_line_is_refused(self):
        # The frozen file takes deletes only: a second copy of a line its base holds once is a line the base lacks.
        lines = self.frozen_base()
        self.commit_base()
        once = [line for line in lines if SLUG_LINE.match(line) and lines.count(line) == 1][0]
        self.put(OLD_NOTES, "\n".join(lines + [once]) + "\n")
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.remedy_names_note_folder(out)

    def test_moved_frozen_line_passes(self):
        # The same text in another place adds no text the base lacks.
        lines = self.frozen_base()
        self.commit_base()
        moved = list(lines)
        first = [line for line in lines if SLUG_LINE.match(line)][0]
        moved.pop(moved.index(first))
        moved.append(first)
        self.put(OLD_NOTES, "\n".join(moved) + "\n")
        self.commit_change()
        numstat = self.git_out("diff", "--numstat", "origin/main", "HEAD", "--", OLD_NOTES).split()[:2]
        self.assertEqual(numstat, ["1", "1"], numstat)  # scope: the line moved, one out and one in
        self.assert_passes()

    def assert_text_split_by_a_separator_is_refused(self, sep):
        # The base holds one line, `- a: first<sep>second`. Its text before `sep` is not a line of the base, so a
        # branch that adds `- a: first` adds a line.
        lines = self.frozen_base()
        base = lines + ["- a: first" + sep + "second"]
        self.put(OLD_NOTES, "\n".join(base) + "\n")
        self.commit_base()
        self.put(OLD_NOTES, "\n".join(base + ["- a: first"]) + "\n")
        self.commit_change()
        numstat = self.git_out("diff", "--numstat", "origin/main", "HEAD", "--", OLD_NOTES).split()[:2]
        self.assertEqual(numstat, ["1", "0"], numstat)  # scope: one line added, nothing else
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.remedy_names_note_folder(out)

    def test_text_before_a_u2028_in_a_base_line_is_not_a_base_line(self):
        self.assert_text_split_by_a_separator_is_refused(" ")

    def test_text_before_a_formfeed_in_a_base_line_is_not_a_base_line(self):
        self.assert_text_split_by_a_separator_is_refused("\x0c")

    def test_base_lines_holding_u2028_formfeed_or_bom_left_unchanged_raise_no_finding(self):
        lines = self.frozen_base()
        extra = ["- a: first second", "- b: first\x0csecond", "﻿- c: first"]
        self.put(OLD_NOTES, "\n".join(lines + extra) + "\n")
        self.commit_base()
        self.put(OLD_NOTES, "\n".join(lines[1:] + extra) + "\n")  # deletes the first real line; the three stay
        self.commit_change()
        numstat = self.git_out("diff", "--numstat", "origin/main", "HEAD", "--", OLD_NOTES).split()[:2]
        self.assertEqual(numstat, ["0", "1"], numstat)  # scope: the file is in the diff, as a delete only
        self.assert_passes()

    def assert_note_file_with_a_separator_passes_the_form_check(self, sep):
        self.roll_out()
        self.commit_base()
        self.put(NOTE % "spin-rate-cap",
                 "- spin-rate-cap: the spin rate" + sep + "is capped (hooks/guard.py) Seen: 2026-11-17 x1\n")
        self.commit_change()
        self.assert_passes()

    def test_note_file_whose_one_line_holds_u2028_passes_the_form_check(self):
        self.assert_note_file_with_a_separator_passes_the_form_check(" ")

    def test_note_file_whose_one_line_holds_formfeed_passes_the_form_check(self):
        self.assert_note_file_with_a_separator_passes_the_form_check("\x0c")

    def test_digits_only_note_slug_is_refused_and_the_remedy_names_the_folder(self):
        # A digits-only slug collides with the old file's `note:<digits>` refs (hooks/feedback_guard.py).
        self.roll_out()
        self.commit_base()
        self.put(NOTE % "1", "- 1: text\n")
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertEqual(flagged(out), [NOTE % "1"], out)
        self.remedy_names_note_folder(out)

    def test_slug_with_digits_and_letters_passes(self):
        self.roll_out()
        self.commit_base()
        self.put(NOTE % "2fa-note", "- 2fa-note: text (hooks/guard.py) Seen: 2026-11-17 x1\n")
        self.commit_change()
        self.assert_passes()

    def lint_after_edit(self, text, base=EDIT_OLD):
        # The base holds `base` in a note file; the branch writes `text` into the same file.
        self.roll_out()
        self.put(NOTE % "edited-note", base)
        self.commit_base()
        self.put(NOTE % "edited-note", text)
        self.commit_change()
        statuses = self.git_out("diff", "--name-status", "origin/main", "HEAD").splitlines()
        self.assertIn("M\t" + NOTE % "edited-note", statuses, statuses)  # scope: the edit is in the diff
        return self.lint()

    def test_edited_note_file_with_a_second_line_is_refused(self):
        rc, out = self.lint_after_edit(EDIT_NEW + "- edited-note: a second line (hooks/guard.py)\n")
        self.assertEqual(rc, 1, out)
        self.assertEqual(flagged(out), [NOTE % "edited-note"], out)

    def test_edited_note_file_whose_slug_differs_from_its_name_is_refused(self):
        rc, out = self.lint_after_edit(MISMATCH_TEXT)
        self.assertEqual(rc, 1, out)
        self.assertEqual(flagged(out), [NOTE % "edited-note"], out)

    def test_edited_note_file_without_a_slug_line_is_refused(self):
        rc, out = self.lint_after_edit(NO_SLUG_LINE + "\n")
        self.assertEqual(rc, 1, out)
        self.assertEqual(flagged(out), [NOTE % "edited-note"], out)

    def test_valid_edit_of_a_note_file_passes(self):
        rc, out = self.lint_after_edit(EDIT_NEW)
        self.assertEqual(rc, 0, out)
        self.assertNotIn("FAIL", out)

    def test_edited_readme_in_the_notes_folder_passes(self):
        # The folder's README is not a note, edited or not.
        self.roll_out()
        self.put(NOTE_DIR + "/README.md", README_TEXT)
        self.commit_base()
        self.put(NOTE_DIR + "/README.md", README_TEXT + "\nA second paragraph.\n")
        self.commit_change()
        self.assert_passes()

    def test_note_file_with_empty_text_after_its_slug_is_refused(self):
        # `- <slug>: ` with nothing after the colon and space is a note with no text. The form check reads the slug only.
        self.roll_out()
        self.commit_base()
        self.put(NOTE % "empty-note", "- empty-note: \n")
        self.put(NOTE % "valid-note", NOTE_TEXT % "valid-note")
        self.commit_change()
        statuses = self.git_out("diff", "--name-status", "origin/main", "HEAD").splitlines()
        self.assertIn("A\t" + NOTE % "empty-note", statuses, statuses)  # scope: the empty note is in the diff
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertEqual(flagged(out), [NOTE % "empty-note"], out)

    def test_note_file_in_a_nested_folder_of_the_note_folder_is_refused(self):
        # Notes are flat: one file per note, directly under the note folder. The valid flat note beside it passes.
        self.roll_out()
        self.commit_base()
        nested = NOTE_DIR + "/sub/nested-note.md"
        self.put(nested, NOTE_TEXT % "nested-note")
        self.put(NOTE % "flat-note", NOTE_TEXT % "flat-note")
        self.commit_change()
        statuses = self.git_out("diff", "--name-status", "origin/main", "HEAD").splitlines()
        self.assertIn("A\t" + nested, statuses, statuses)  # scope: the nested note is in the diff
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertEqual(flagged(out), [nested], out)

    # Seen (decision notes-sightings-expiry). A note file's line may carry `Seen: YYYY-MM-DD xN`. An added note needs a
    # valid one, and a count of 2 or more is a debt. An edit or a rename keeps the base's count and its field. No case
    # here moves a fielded date at the same count: only a repeat sighting refreshes Seen (item 547 b).

    def add_note_file(self, slug, field):
        """Adds one note file, with `field` as its Seen field (None for no field), to a base that holds no note."""
        self.roll_out()
        self.commit_base()
        self.put(NOTE % slug, note_line(slug, field))
        self.commit_change()
        statuses = self.git_out("diff", "--name-status", "origin/main", "HEAD").splitlines()
        self.assertIn("A\t" + NOTE % slug, statuses, statuses)  # scope: the note file is in the diff

    def assert_added_note_refused(self, slug, field, cause):
        self.add_note_file(slug, field)
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertEqual(flagged(out), [NOTE % slug], out)
        self.assertIn(cause, self.fail_line(out, slug), out)

    def test_added_note_without_seen_is_refused(self):
        self.assert_added_note_refused("seen-missing", None, "Seen")

    def test_added_note_at_two_sightings_is_refused_as_a_debt(self):
        self.assert_added_note_refused("seen-twice", seen(0, 2), "debt")

    def test_added_note_seen_31_days_old_is_refused(self):
        self.assert_added_note_refused("seen-stale", seen(-31, 1), "Seen")

    def test_added_note_seen_in_the_future_is_refused(self):
        self.assert_added_note_refused("seen-early", seen(1, 1), "Seen")

    def test_added_note_with_a_count_of_zero_is_refused(self):
        self.assert_added_note_refused("seen-zero", "Seen: %s x0" % day(0), "Seen")

    def test_added_note_with_a_date_that_is_not_a_day_is_refused(self):
        self.assert_added_note_refused("seen-feb30", "Seen: 2026-02-30 x1", "Seen")

    def test_added_note_seen_today_passes(self):
        self.add_note_file("seen-today", seen(0, 1))
        self.assert_passes()

    def test_added_note_seen_30_days_old_passes(self):
        # "No more than 30 days old": the window's edge passes, and the 31-day case above is one day past it.
        self.add_note_file("seen-edge", seen(-30, 1))
        self.assert_passes()

    def test_edit_keeping_an_old_seen_date_and_count_passes(self):
        # An edit is not judged on age: it keeps the old date and count, so it passes. Adding such a note is refused.
        rc, out = self.lint_after_edit("- edited-note: the reworded note text (hooks/guard.py) " + seen(-40, 1) + "\n",
                                       base=note_line("edited-note", seen(-40, 1)))
        self.assertEqual(rc, 0, out)
        self.assertNotIn("FAIL", out)

    def test_added_note_with_an_old_seen_date_is_refused(self):
        self.assert_added_note_refused("seen-old-add", seen(-40, 1), "Seen")

    def test_deleted_note_at_two_sightings_passes(self):
        # A deleted note file passes whatever its count: the x2 remedy is to delete it.
        self.roll_out()
        self.put(NOTE % "seen-gone", note_line("seen-gone", seen(-1, 2)))
        self.commit_base()
        self.delete(NOTE % "seen-gone")
        self.commit_change()
        statuses = self.git_out("diff", "--name-status", "origin/main", "HEAD").splitlines()
        self.assertIn("D\t" + NOTE % "seen-gone", statuses, statuses)  # scope: the delete is in the diff
        self.assert_passes()

    def test_edit_that_drops_the_seen_field_is_refused(self):
        rc, out = self.lint_after_edit(note_line("edited-note"), base=note_line("edited-note", seen(-1, 1)))
        self.assertEqual(rc, 1, out)
        self.assertEqual(flagged(out), [NOTE % "edited-note"], out)

    def test_edit_that_lowers_the_sighting_count_is_refused(self):
        rc, out = self.lint_after_edit(note_line("edited-note", seen(-1, 1)),
                                       base=note_line("edited-note", seen(-1, 3)))
        self.assertEqual(rc, 1, out)
        self.assertEqual(flagged(out), [NOTE % "edited-note"], out)

    def lint_after_rename(self, base, text):
        # The base holds `base` as the note RENAME_FROM. The branch renames it to RENAME_TO and writes `text` there.
        self.roll_out()
        self.put(NOTE % RENAME_FROM, base)
        self.commit_base()
        self.move(NOTE % RENAME_FROM, NOTE % RENAME_TO)
        self.put(NOTE % RENAME_TO, text)
        self.commit_change()
        statuses = self.git_out("diff", "--name-status", "origin/main", "HEAD").splitlines()
        renamed = [s.split("\t")[1:] for s in statuses if s.startswith("R")]
        want = [[NOTE % RENAME_FROM, NOTE % RENAME_TO]]
        self.assertEqual(renamed, want, statuses)  # scope: the rename is in the diff
        return self.lint()

    def test_rename_that_drops_the_seen_field_is_refused(self):
        rc, out = self.lint_after_rename(note_line(RENAME_FROM, seen(-1, 1)), note_line(RENAME_TO))
        self.assertEqual(rc, 1, out)
        self.assertEqual(flagged(out), [NOTE % RENAME_TO], out)

    def test_rename_that_lowers_the_sighting_count_is_refused(self):
        rc, out = self.lint_after_rename(note_line(RENAME_FROM, seen(-1, 3)), note_line(RENAME_TO, seen(-1, 1)))
        self.assertEqual(rc, 1, out)
        self.assertEqual(flagged(out), [NOTE % RENAME_TO], out)

    def test_rename_that_keeps_the_count_and_the_date_passes(self):
        rc, out = self.lint_after_rename(note_line(RENAME_FROM, seen(-1, 1)), note_line(RENAME_TO, seen(-1, 1)))
        self.assertEqual(rc, 0, out)
        self.assertNotIn("FAIL", out)

    def test_added_line_in_the_frozen_file_is_still_refused_beside_a_seen_note(self):
        lines = self.frozen_base()
        self.commit_base()
        self.put(OLD_NOTES, "\n".join(lines + [NEW_LINE]) + "\n")
        self.put(NOTE % "seen-beside", note_line("seen-beside", seen(0, 1)))
        self.commit_change()
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertNotIn(NOTE % "seen-beside", flagged(out), out)  # the valid note passes; the frozen line is refused
        self.remedy_names_note_folder(out)

    def test_a_real_note_form_passes_as_an_added_file(self):
        # One note's text as main holds it, with its Seen field. It reads no live file: a note added later, dated after
        # PINNED_TODAY, must not turn this case red.
        self.roll_out()
        self.commit_base()
        self.put(NOTE % "ps-scriptblock-path-refused", REAL_NOTE_LINE)
        self.commit_change()
        statuses = self.git_out("diff", "--name-status", "origin/main", "HEAD").splitlines()
        self.assertIn("A\t" + NOTE % "ps-scriptblock-path-refused", statuses, statuses)  # scope: it is an added file
        self.assert_passes()

    # Debt files. A Seen line at column one, or after one leading "- ", is checked when present. No age limit for debts.

    def assert_debt_seen_refused(self, slug, seen_line):
        self.commit_base()
        self.put("debts/%s.md" % slug, debt_body(slug, seen_line))
        self.commit_change()
        statuses = self.git_out("diff", "--name-status", "origin/main", "HEAD").splitlines()
        self.assertIn("A\tdebts/%s.md" % slug, statuses, statuses)  # scope: the debt file is in the diff
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertEqual(flagged(out), ["debts/%s.md" % slug], out)

    def test_debt_seen_without_a_count_is_refused(self):
        self.assert_debt_seen_refused("seen-no-count", "Seen: %s" % day(0))

    def test_debt_seen_with_a_count_of_zero_is_refused(self):
        self.assert_debt_seen_refused("seen-zero", "Seen: %s x0" % day(0))

    def test_debt_seen_with_a_date_that_is_not_a_day_is_refused(self):
        self.assert_debt_seen_refused("seen-feb30", "Seen: 2026-02-30 x2")

    def test_debt_seen_with_a_word_for_a_date_is_refused(self):
        self.assert_debt_seen_refused("seen-word", "Seen: soon x2")

    def test_debt_seen_at_two_sightings_passes_at_any_age_in_either_form(self):
        self.commit_base()
        self.put("debts/seen-old.md", debt_body("seen-old", seen(-400, 2)))
        self.put("debts/seen-bullet.md", debt_body("seen-bullet", "- " + seen(0, 1)))
        self.commit_change()
        self.assert_passes()

    def test_debt_with_a_future_seen_date_is_refused(self):
        self.assert_debt_seen_refused("seen-future", seen(1, 1))

    def test_edited_debt_whose_seen_turns_malformed_is_refused(self):
        self.put("debts/edited-debt.md", debt_body("edited-debt", seen(-1, 1)))
        self.commit_base()
        self.put("debts/edited-debt.md", debt_body("edited-debt", "Seen: 2026-02-30 x1"))
        self.commit_change()
        statuses = self.git_out("diff", "--name-status", "origin/main", "HEAD").splitlines()
        self.assertIn("M\tdebts/edited-debt.md", statuses, statuses)  # scope: the debt edit is in the diff
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertEqual(flagged(out), ["debts/edited-debt.md"], out)

    def test_renamed_debt_whose_seen_is_in_the_future_is_refused(self):
        body = "# Shared gap\n\nWhat. A gap with a fix named.\n"  # the same text under a new name: git reads a rename
        self.put("debts/old-gap.md", body + seen(-1, 1) + "\n")
        self.commit_base()
        self.move("debts/old-gap.md", "debts/new-gap.md")
        self.put("debts/new-gap.md", body + seen(1, 1) + "\n")
        self.commit_change()
        statuses = self.git_out("diff", "--name-status", "origin/main", "HEAD").splitlines()
        renamed = [s.split("\t")[1:] for s in statuses if s.startswith("R")]
        want = [["debts/old-gap.md", "debts/new-gap.md"]]
        self.assertEqual(renamed, want, statuses)  # scope: the rename is in the diff
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertEqual(flagged(out), ["debts/new-gap.md"], out)

    # --next-debt: the debt with the highest count. A debt with no Seen line counts as x1 with no date. A count tie goes
    # to the oldest date, a debt with no date after the dated ones, then the slug.

    def commit_debts(self, *debts):
        """Commits each (slug, Seen line or None) debt on a base, so the folder read and the commit read agree."""
        self.commit_base()
        for slug, seen_line in debts:
            self.put("debts/%s.md" % slug, debt_body(slug, seen_line))
        self.commit_change()

    def assert_next_debt(self, expected, *slugs):
        listed = self.git_out("ls-files", "--", "debts").split()
        for slug in slugs:  # scope: each debt the case names is in the tree before the check reads the folder
            self.assertIn("debts/%s.md" % slug, listed, listed)
        rc, out = self.lint("--next-debt")
        self.assertEqual(rc, 0, out)
        self.assertEqual(out.strip(), expected, out)

    def test_next_debt_names_the_debt_with_the_highest_count(self):
        self.commit_debts(("alpha", seen(-30, 2)), ("beta", "- " + seen(-1, 5)), ("gamma", seen(-60, 3)))
        self.assert_next_debt("beta", "alpha", "beta", "gamma")

    def test_next_debt_breaks_a_count_tie_by_the_oldest_date(self):
        self.commit_debts(("aaa-later", seen(-1, 3)), ("zzz-earlier", seen(-20, 3)))  # the slug order picks the first
        self.assert_next_debt("zzz-earlier", "aaa-later", "zzz-earlier")

    def test_next_debt_breaks_a_date_tie_by_the_slug(self):
        self.commit_debts(("zeta", seen(-5, 3)), ("alpha", seen(-5, 3)))
        self.assert_next_debt("alpha", "zeta", "alpha")

    def test_next_debt_ranks_a_dated_debt_above_an_undated_one_of_the_same_count(self):
        # The undated debt counts x1 and sorts first by slug, so only the rule about dates picks the other one.
        self.commit_debts(("aaa-undated", None), ("zzz-dated", seen(-3, 1)))
        self.assert_next_debt("zzz-dated", "aaa-undated", "zzz-dated")

    def test_next_debt_names_a_lone_debt_with_no_seen_line(self):
        self.commit_debts(("quiet", None))
        self.assert_next_debt("quiet", "quiet")

    def test_next_debt_ignores_the_notes_file_the_readme_and_the_note_folder(self):
        self.commit_debts(("small", seen(-1, 1)))
        self.put(DEBT_README, "# Debts\n\nSeen: %s x9\n" % day(-1))
        self.put(DEBT_NOTES, "- loud-note: a gap (hooks/guard.py) Seen: %s x9\n" % day(-1))
        self.put(NOTE % "loud-note", note_line("loud-note", seen(-1, 9)))
        self.commit_change()
        self.assert_next_debt("small", "small")

    # --debt-flow START END: the debt files opened and closed between two refs. The window includes START itself, and a
    # debt added and deleted inside it is in neither list. The notes file and the README are not debts.

    def test_debt_flow_counts_the_start_commit_and_nets_out_a_debt_opened_and_closed_inside_the_window(self):
        self.put("debts/old-debt.md", debt_body("old-debt"))
        self.commit_base()  # the parent of START
        self.put("debts/start-debt.md", debt_body("start-debt"))
        self.commit_change()
        start = self.git_out("rev-parse", "HEAD").strip()  # START
        self.put("debts/netted-debt.md", debt_body("netted-debt"))
        self.commit_change()
        self.delete("debts/netted-debt.md", "debts/old-debt.md")
        self.put("debts/fresh-debt.md", debt_body("fresh-debt"))
        self.commit_change()
        at_start = self.git_out("show", "--format=", "--name-status", start).splitlines()
        self.assertIn("A\tdebts/start-debt.md", at_start, at_start)  # scope: START itself adds a debt
        window = self.git_out("log", "--format=", "--name-status", start + "..HEAD").splitlines()
        self.assertIn("A\tdebts/netted-debt.md", window, window)  # scope: netted-debt is added inside the window
        self.assertIn("D\tdebts/netted-debt.md", window, window)  # and deleted inside it
        rc, out = self.lint("--debt-flow", start, "HEAD")
        self.assertEqual(rc, 0, out)
        lines = out.splitlines()
        self.assertEqual(lines[:1], ["debts opened 2, closed 1"], out)
        self.assertEqual(sorted(lines[1:]), ["+ fresh-debt", "+ start-debt", "- old-debt"], out)

    def test_debt_flow_counts_a_root_start_commit_from_the_empty_tree(self):
        self.put("debts/root-debt.md", debt_body("root-debt"))
        self.commit_base()  # START has no parent
        start = self.git_out("rev-parse", "HEAD").strip()
        parents = self.git_out("rev-list", "--parents", "-n", "1", start).split()
        self.assertEqual(len(parents), 1, parents)  # scope: START is a root commit
        self.put("debts/later-debt.md", debt_body("later-debt"))
        self.commit_change()
        rc, out = self.lint("--debt-flow", start, "HEAD")
        self.assertEqual(rc, 0, out)
        lines = out.splitlines()
        self.assertEqual(lines[:1], ["debts opened 2, closed 0"], out)
        self.assertEqual(sorted(lines[1:]), ["+ later-debt", "+ root-debt"], out)

    def test_debt_flow_with_only_the_readme_and_the_notes_file_changed_names_no_debt(self):
        self.put(DEBT_README, "# Debts\n\nOne debt per file.\n")
        self.put(DEBT_NOTES, "- old-line: a gap (hooks/guard.py)\n")
        self.commit_base()
        self.put(DEBT_README, "# Debts\n\nOne debt per file, as before.\n")
        self.put(DEBT_NOTES, "- old-line: a gap (hooks/guard.py)\n- new-line: a gap (hooks/guard.py)\n")
        self.commit_change()
        start = self.git_out("rev-parse", "HEAD").strip()
        changed = self.git_out("show", "--format=", "--name-status", start).splitlines()
        want = sorted(["M\t" + DEBT_NOTES, "M\t" + DEBT_README])
        self.assertEqual(sorted(changed), want, changed)  # scope: both are in START
        rc, out = self.lint("--debt-flow", start, "HEAD")
        self.assertEqual(rc, 0, out)
        self.assertEqual(out.splitlines(), ["debts opened 0, closed 0"], out)

    def test_debt_flow_with_a_start_that_is_not_a_commit_is_unknown(self):
        self.commit_base()
        rc, out = self.lint("--debt-flow", "no-such-start", "HEAD")
        self.assertEqual(rc, 1, out)
        self.assertIn("UNKNOWN", out, out)

    def test_debt_flow_outside_a_repo_is_unknown(self):
        outside = tempfile.mkdtemp(prefix="outside_", dir=RUN_FOLDER)  # a folder in the run folder, no repo above it
        ceiling = {"GIT_CEILING_DIRECTORIES": RUN_FOLDER}  # git stops searching at the run folder
        probe = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=outside, env=clean_env(**ceiling),
                               capture_output=True, text=True)
        self.assertNotEqual(probe.returncode, 0, "the folder is inside a repo, so the case proves nothing")  # scope
        rc, out = self.run_check(outside, "--debt-flow", "HEAD", "HEAD", **ceiling)
        self.assertEqual(rc, 1, out)
        self.assertIn("UNKNOWN", out, out)

    def test_debt_flow_in_a_shallow_clone_is_unknown(self):
        # A shallow clone's boundary commit has no parent, so its window would count every debt as opened.
        self.commit_base()
        self.put("debts/shallow-old.md", debt_body("shallow-old"))
        self.commit_change()
        self.put("debts/shallow-new.md", debt_body("shallow-new"))
        self.commit_change()
        clone = os.path.join(RUN_FOLDER, "shallow-clone")
        subprocess.run(["git", "clone", "-q", "--depth", "1", "file://" + self.tree, clone], check=True,
                       capture_output=True, text=True, env=clean_env())
        probe = subprocess.run(["git", "rev-parse", "--is-shallow-repository"], cwd=clone, env=clean_env(),
                               capture_output=True, text=True)
        self.assertEqual(probe.stdout.strip(), "true", probe.stdout + probe.stderr)  # scope: the clone is shallow
        parents = subprocess.run(["git", "rev-list", "--parents", "-n", "1", "HEAD"], cwd=clone, env=clean_env(),
                                 capture_output=True, text=True).stdout.split()
        self.assertEqual(len(parents), 1, parents)  # scope: HEAD is the boundary commit, with no parent
        rc, out = self.run_check(clone, "--debt-flow", "HEAD", "HEAD")
        self.assertIn("UNKNOWN", out, out)
        self.assertNotIn("debts opened", out, out)
        self.assertEqual(rc, 1, out)

    # The check's date is Central's: hooks/local_time.py is the one home of the Central clock, and LOCAL_TIME_NOW pins
    # it. FIXED_TODAY is removed here, and the machine's zone (TZ) is set far from Central, so neither can supply it.

    def test_central_today_is_the_check_date_with_no_fixed_today(self):
        self.add_note_file("central-today", "Seen: 2000-01-17 x1")
        rc, out = self.run_check(self.tree, FIXED_TODAY=None, LOCAL_TIME_NOW=CENTRAL_NOON, TZ=MACHINE_ZONE)
        self.assertEqual(rc, 0, out)
        self.assertNotIn("FAIL", out)

    def test_central_tomorrow_is_refused_as_future_with_no_fixed_today(self):
        self.add_note_file("central-tomorrow", "Seen: 2000-01-18 x1")
        rc, out = self.run_check(self.tree, FIXED_TODAY=None, LOCAL_TIME_NOW=CENTRAL_NOON, TZ=MACHINE_ZONE)
        self.assertEqual(rc, 1, out)
        self.assertIn("in the future", self.fail_line(out, "central-tomorrow"), out)

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


READY_STEP = "Record slug length"  # the step that reads the section folder; also its name in .github/workflows/checks.yml
# The text hooks/test_guard.py looks for when a duplicate number stops its run: `section number <n> is on <k> section files`.
RUNNER_CLASH = re.compile(r"section number (\d+) is on (\d+) section files")


def runner_clash_texts():
    """Each string of hooks/test_guard.py that is the whole of RUNNER_CLASH, read by ast: the runner holds the one copy."""
    with open(RUNNER, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and RUNNER_CLASH.fullmatch(n.value)]


class SectionClashTests(unittest.TestCase):
    """Two guard test section files on one number: the fault names each file on it and the next free number, one above
    the highest header, so the branch that lands second renumbers without reading the other (decision
    section-number-clash-ready). No case needs git: each writes real section files in a run folder and reads them as
    the check and the runner do, so a run on an old tree reaches an assert."""

    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="sec_", dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)

    def faults(self, numbers_by_name):
        """The faults of a folder that holds one section file per (name, header number) pair."""
        for name, n in numbers_by_name.items():
            with open(os.path.join(self.folder, name), "w", encoding="utf-8", newline="\n") as f:
                f.write(section_text(n))
        return _guard_sections.faults(_guard_sections.read(self.folder))

    def assert_names_files_and_next_free(self, bad, holders, next_free):
        """Scope first: the faults are on `holders` and no other file. Then each message names every holder and `next_free`."""
        self.assertEqual(sorted(os.path.basename(path) for path, _ in bad), sorted(holders),
                         "scope: the faults are not on the clashing files alone")
        for path, message in bad:
            for holder in holders:
                self.assertIn(holder, message, "the fault on %s does not name %s, a file on the same number" % (path, holder))
            self.assertIn(str(next_free), message, "the fault on %s does not name the next free number, %d" % (path, next_free))

    def test_two_files_on_one_number_name_both_files_and_the_next_free_number(self):
        # The clash is on 43700 and the highest header is 43725: the next free number is 43726, not 43701.
        bad = self.faults({"s43700-a.py": 43700, "s43700-b.py": 43700, "s43725-c.py": 43725})
        self.assert_names_files_and_next_free(bad, ["s43700-a.py", "s43700-b.py"], 43726)

    def test_three_files_on_one_number_name_all_three(self):
        bad = self.faults({"s43700-a.py": 43700, "s43700-b.py": 43700, "s43700-c.py": 43700, "s43725-d.py": 43725})
        self.assert_names_files_and_next_free(bad, ["s43700-a.py", "s43700-b.py", "s43700-c.py"], 43726)

    def test_a_full_size_folder_flags_only_the_clashing_pair(self):
        files = {"s%d-x.py" % n: n for n in range(43000, 43200)}  # 200 files on 200 numbers
        files["s43100-dup.py"] = 43100
        bad = self.faults(files)
        self.assert_names_files_and_next_free(bad, ["s43100-dup.py", "s43100-x.py"], 43200)

    def test_distinct_numbers_give_no_fault(self):
        # The green control beside the reds: each name agrees with its header and no number repeats.
        self.assertEqual(self.faults({"s43700-a.py": 43700, "s43701-b.py": 43701, "s43725-c.py": 43725}), [])

    def test_an_empty_folder_gives_no_fault(self):
        self.assertEqual(_guard_sections.faults(_guard_sections.read(self.folder)), [])

    def test_the_message_keeps_the_text_the_runner_looks_for(self):
        # hooks/test_guard.py reads the stop of a duplicate number by this text, so the new tail must follow it.
        texts = runner_clash_texts()
        self.assertEqual(len(texts), 1, "scope: hooks/test_guard.py holds %d texts of the form %r, not one"
                         % (len(texts), RUNNER_CLASH.pattern))
        number, count = (int(g) for g in RUNNER_CLASH.fullmatch(texts[0]).groups())
        bad = self.faults({"s%05d-%d.py" % (number, i): number for i in range(count)})
        self.assertEqual(len(bad), count, "scope: %d files on section %d did not fault once each" % (count, number))
        for name, message in bad:
            self.assertIn(texts[0], message, "the fault on %s no longer holds %r, the text hooks/test_guard.py reads"
                          % (name, texts[0]))

    def test_the_check_names_the_clashing_files_and_the_next_free_number(self):
        # The check's own read of a root: its paths, with the same message. The runner file is the minimal one
        # rule_audit.section_dir reads, so the root needs no git.
        root = tempfile.mkdtemp(prefix="sec_root_", dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        os.makedirs(os.path.join(root, "hooks"))
        with open(os.path.join(root, "hooks", "test_guard.py"), "w", encoding="utf-8", newline="\n") as f:
            f.write("import os\nHERE = os.path.dirname(os.path.abspath(__file__))\n"
                    'SECTION_DIR = os.path.join(HERE, "..", "tests", "guard")\n')
        os.makedirs(os.path.join(root, *SECTIONS.split("/")))
        for name, n in (("s43700-a.py", 43700), ("s43700-b.py", 43700), ("s43725-c.py", 43725)):
            with open(os.path.join(root, *SECTIONS.split("/"), name), "w", encoding="utf-8", newline="\n") as f:
                f.write(section_text(n))
        spec = importlib.util.spec_from_file_location("check_record_slugs_sections", MODULE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        bad = module.section_faults(root)
        self.assertEqual(sorted(path for path, _ in bad), [SECTIONS + "/s43700-a.py", SECTIONS + "/s43700-b.py"],
                         "scope: the check names paths of the clashing files below the root, and no other")
        self.assert_names_files_and_next_free(bad, ["s43700-a.py", "s43700-b.py"], 43726)

    def test_the_ready_run_reads_the_record_slug_step(self):
        # A draft marked ready on a tree older than main meets a clash only when the ready run reads this step.
        with open(STAMP, encoding="utf-8") as f:
            config = json.load(f)
        checks = config.get("merge", {}).get("readyChecks")
        self.assertIsInstance(checks, list, "scope: .github/stamp.json declares no merge.readyChecks list")
        self.assertIn(READY_STEP, checks, "merge.readyChecks does not list %r, so the ready run never reads a section clash"
                      % READY_STEP)


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
