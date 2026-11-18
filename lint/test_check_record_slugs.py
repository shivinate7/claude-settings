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
RUNNER = os.path.join(HERE, "..", "hooks", "test_guard.py")  # its SECTION_DIR names the section folder the check reads
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
# One file per note: the frozen notes file takes deletes only, and each note is a file under the note folder.
REPO = os.path.dirname(HERE)
OLD_NOTES = "docs/debts/notes.md"  # the frozen notes file
NOTE_DIR = "docs/notes"
NOTE = NOTE_DIR + "/%s.md"  # a note file, named by its slug
SLUG_MAX = "wheel-speed-cap-" + "abcdefghijklmnop"  # 32 characters: the longest slug a note file may have
SLUG_LONG = SLUG_MAX + "q"  # 33 characters
SLUG_LINE = re.compile(r"^- [a-z0-9-]+: ")  # a note line in the `- slug: text` form
NOTE_TEXT = "- %s: the spin rate is capped at twelve degrees per frame (hooks/guard.py)\n"
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
        """A refusal line names the note folder, and no line that names the folder also names the frozen file."""
        lines = out.splitlines()
        self.assertTrue(any(NOTE_DIR + "/" in line for line in lines), out)
        self.assertFalse(any(NOTE_DIR + "/" in line and OLD_NOTES in line for line in lines), out)

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
        self.put(NOTE % "ansi-c-escape-not-decoded", ANSI_LINE + "\n")
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
        self.put(NOTE % "spin-rate-cap", "- spin-rate-cap: the spin rate" + sep + "is capped (hooks/guard.py)\n")
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
        self.assertNotIn(OLD_NOTES, out)

    def test_slug_with_digits_and_letters_passes(self):
        self.roll_out()
        self.commit_base()
        self.put(NOTE % "2fa-note", "- 2fa-note: text (hooks/guard.py)\n")
        self.commit_change()
        self.assert_passes()

    def lint_after_edit(self, text):
        # The base holds EDIT_OLD in a note file; the branch writes `text` into the same file.
        self.roll_out()
        self.put(NOTE % "edited-note", EDIT_OLD)
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
