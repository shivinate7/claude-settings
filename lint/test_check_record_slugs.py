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
# The whole-tree rules, check_gloss and check_links, take a repo root. Their cases build these records under the root.
TARGET = "docs/decisions/target-rule.md"  # the decision that other records cite
CITER = "docs/decisions/citing-record.md"  # a decision that cites the target
TARGET_DEBT = "docs/debts/target-debt.md"  # a debt that a decision cites
CITER_DEBT = "docs/debts/citing-debt.md"  # a debt that cites the target
LINKED_DEBT = "docs/debts/linked-debt.md"  # a debt whose Decision part a case sets
LIVE_DEBT = "docs/debts/live-debt.md"  # a debt that a gap section may name
OTHER_DEBT = "docs/debts/other-debt.md"  # a debt that a gap section names
GAP_RULE = "docs/decisions/gap-rule.md"  # a decision with a gap section
PLAIN_RULE = "docs/decisions/plain-rule.md"  # a decision with no gap section
GLOSS = "(the rule that sets the limit)"  # a gloss of two or more words
LIVE_TEXT = "# Live debt\n\n**Decision.** none. Its own finding.\n"  # a debt with a valid Decision part
LIVE_LINKED = "# Live debt\n\n**Decision.** `gap-rule` %s.\n" % GLOSS  # a debt that cites the gap decision
REPO = os.path.dirname(HERE)  # the repo whose real records the whole-tree rules read

RULES = None  # the module under test, loaded once per run by rules_module()
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


def rules_module():
    """The module under test, loaded without running its command line, as ImportTests loads it. One load per run."""
    global RULES
    if RULES is None:
        spec = importlib.util.spec_from_file_location("record_slugs_rules_under_test", MODULE)
        RULES = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(RULES)
    return RULES


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

    # Whole-tree rules. check_gloss and check_links return problem strings for a root. Each case builds its
    # records under the root and calls the rule on it.

    def rule(self, name):
        """The whole-tree rule `name` of the module under test. A module that lacks it fails the case by assert."""
        fn = getattr(rules_module(), name, None)
        self.assertIsNotNone(fn, "%s defines no %s(root)" % (os.path.basename(MODULE), name))
        return fn

    def have(self, *rels):
        """Scope first: the fixture holds each record before the rule reads it."""
        for rel in rels:
            self.assertTrue(os.path.isfile(os.path.join(self.tree, *rel.split("/"))), "fixture lacks " + rel)

    def assert_one_problem(self, problems, *parts):
        """Exactly one problem, and it names each of `parts`: the file and the slug."""
        self.assertEqual(len(problems), 1, problems)
        for part in parts:
            self.assertIn(part, problems[0])

    def gloss_case(self, text, rel=CITER):
        """The target record, and `rel` holding `text`. Returns check_gloss on the tree."""
        self.put(TARGET)
        self.put(rel, text)
        self.have(TARGET, rel)
        return self.rule("check_gloss")(self.tree)

    def link_case(self, decision_line, rel=LINKED_DEBT):
        """The target record, and a debt holding `decision_line`. Returns check_links on the tree."""
        self.put(TARGET)
        self.put(rel, "# Linked debt\n\n%s\n" % decision_line)
        self.have(TARGET, rel)
        return self.rule("check_links")(self.tree)

    # check_gloss: the first backticked cite of another record carries a gloss of two or more words.

    def test_gloss_present_passes(self):
        self.assertEqual(self.gloss_case("See `target-rule` %s.\n" % GLOSS), [])

    def test_gloss_bare_first_cite_fails(self):
        self.assert_one_problem(self.gloss_case("See `target-rule` for the limit.\n"),
                                "citing-record.md", "target-rule")

    def test_gloss_bare_first_cite_then_glossed_second_still_fails(self):
        text = "See `target-rule` for it. Later `target-rule` %s.\n" % GLOSS
        self.assert_one_problem(self.gloss_case(text), "citing-record.md", "target-rule")

    def test_gloss_bare_later_cite_after_glossed_first_passes(self):
        text = "See `target-rule` %s. Again `target-rule` here.\n" % GLOSS
        self.assertEqual(self.gloss_case(text), [])

    def test_gloss_own_slug_is_exempt(self):
        self.assertEqual(self.gloss_case("This record is `citing-record`, bare.\n"), [])

    def test_gloss_backticked_non_slug_passes(self):
        self.assertEqual(self.gloss_case("Run `npm ci` and `grep` first.\n"), [])

    def test_gloss_one_word_gloss_fails(self):
        self.assert_one_problem(self.gloss_case("See `target-rule` (x).\n"), "citing-record.md", "target-rule")

    def test_gloss_debt_file_bare_cite_fails(self):
        text = "See `target-rule` for the limit.\n"
        self.assert_one_problem(self.gloss_case(text, CITER_DEBT), "citing-debt.md", "target-rule")

    def test_gloss_decision_bare_cite_of_a_debt_slug_fails(self):
        # A slug is a file stem in either record folder, so a debt slug cited from a decision needs a gloss too.
        self.put(TARGET_DEBT)
        self.put(CITER, "See `target-debt` for the limit.\n")
        self.have(TARGET_DEBT, CITER)
        self.assert_one_problem(self.rule("check_gloss")(self.tree), "citing-record.md", "target-debt")

    def test_gloss_readme_and_notes_are_not_checked(self):
        self.put(TARGET)
        self.put("docs/debts/README.md", "A bare cite: `target-rule`.\n")
        self.put("docs/debts/notes.md", "- A bare cite: `target-rule`.\n")
        self.have(TARGET, "docs/debts/README.md", "docs/debts/notes.md")
        self.assertEqual(self.rule("check_gloss")(self.tree), [])

    def test_gloss_lone_apostrophe_does_not_hide_a_bare_cite(self):
        self.assert_one_problem(self.gloss_case("Don't reuse `target-rule` here.\n"), "citing-record.md", "target-rule")

    def test_gloss_full_size_slug_bare_cite_fails(self):
        slug = OK[:-3]  # 32 characters, the longest slug the check allows
        self.put("docs/decisions/" + OK)
        self.put(CITER, "See `%s` for the limit.\n" % slug)
        self.have("docs/decisions/" + OK, CITER)
        self.assert_one_problem(self.rule("check_gloss")(self.tree), "citing-record.md", slug)

    def test_gloss_empty_records_pass(self):
        self.assertFalse(os.path.isdir(os.path.join(self.tree, "docs")))  # scope: the tree holds no records
        self.assertEqual(self.rule("check_gloss")(self.tree), [])

    # check_links: a debt's Decision part is `none` or names an existing decision. A gap section lists its debts.

    def test_debt_decision_none_passes(self):
        for line in ("**Decision.** none. No decision fits.", "**Decision.** `none`. No decision fits.",
                     "- **Decision.** `none`. No decision fits."):
            with self.subTest(line=line):
                self.assertEqual(self.link_case(line), [])

    def test_debt_decision_naming_a_decision_passes(self):
        for line in ("**Decision.** `target-rule` %s." % GLOSS, "**Decision.** target-rule %s." % GLOSS,
                     "- **Decision.** `target-rule` %s." % GLOSS):
            with self.subTest(line=line):
                self.assertEqual(self.link_case(line), [])

    def test_debt_decision_naming_no_decision_fails(self):
        self.assert_one_problem(self.link_case("**Decision.** `no-such-rule` %s." % GLOSS),
                                "linked-debt.md", "no-such-rule")

    def test_debt_decision_naming_a_debt_fails(self):
        self.put(TARGET_DEBT)
        self.assert_one_problem(self.link_case("**Decision.** `target-debt` %s." % GLOSS),
                                "linked-debt.md", "target-debt")

    def test_debt_decision_without_a_slug_fails(self):
        self.assert_one_problem(self.link_case("**Decision.** Nothing names it here."), "linked-debt.md")

    def test_debt_without_a_decision_part_fails(self):
        self.put(TARGET)
        self.put(LINKED_DEBT, "# Linked debt\n\n**What.** A finding.\n")
        self.have(TARGET, LINKED_DEBT)
        self.assert_one_problem(self.rule("check_links")(self.tree), "linked-debt.md")

    def test_stale_debt_in_a_gap_section_fails(self):
        for heading in ("## Safety holes, named", "## Known gaps", "## Gaps"):
            with self.subTest(heading=heading):
                self.put(GAP_RULE, "# Gap rule\n\n%s\n\nDebt: `vanished-debt` %s.\n" % (heading, GLOSS))
                self.assert_one_problem(self.rule("check_links")(self.tree), "gap-rule.md", "vanished-debt")

    def test_stale_debt_in_a_bullet_list_fails(self):
        self.put(LIVE_DEBT, LIVE_TEXT)
        self.put(GAP_RULE, "# Gap rule\n\n## Known gaps\n\nDebts:\n- `live-debt` %s.\n- `vanished-debt` %s.\n"
                 % (GLOSS, GLOSS))
        self.have(LIVE_DEBT, GAP_RULE)
        self.assert_one_problem(self.rule("check_links")(self.tree), "gap-rule.md", "vanished-debt")

    def test_stale_debt_behind_a_paren_label_fails(self):
        self.put(GAP_RULE, "# Gap rule\n\n## Gaps\n\n- Reader gap (debt `vanished-debt`).\n")
        self.assert_one_problem(self.rule("check_links")(self.tree), "gap-rule.md", "vanished-debt")

    def test_note_and_unlabelled_slugs_are_not_debts(self):
        # A note names no debt file, and a backticked slug with no debt label is not a debt listing.
        self.put(GAP_RULE, "# Gap rule\n\n## Known gaps\n\nNote: `some-note` %s.\n\nThe check reads `code-check` too.\n"
                 % GLOSS)
        self.have(GAP_RULE)
        self.assertEqual(self.rule("check_links")(self.tree), [])

    def test_span_inside_a_debt_gloss_is_not_a_debt(self):
        self.put(LIVE_DEBT, LIVE_TEXT)
        self.put(GAP_RULE, "# Gap rule\n\n## Known gaps\n\nDebt: `live-debt` (the reader skips `vanished-thing`).\n")
        self.have(LIVE_DEBT, GAP_RULE)
        self.assertEqual(self.rule("check_links")(self.tree), [])

    def test_stale_debt_outside_the_gap_sections_passes(self):
        self.put(GAP_RULE, "# Gap rule\n\n## The ruling\n\nDebt: `vanished-debt` %s.\n" % GLOSS)
        self.have(GAP_RULE)
        self.assertEqual(self.rule("check_links")(self.tree), [])

    def test_debt_citing_a_gap_decision_must_be_named_there(self):
        self.put(LIVE_DEBT, LIVE_LINKED)
        self.put(OTHER_DEBT, LIVE_TEXT)
        self.put(GAP_RULE, "# Gap rule\n\n## Known gaps\n\nDebts:\n- `other-debt` %s.\n" % GLOSS)
        self.have(LIVE_DEBT, OTHER_DEBT, GAP_RULE)
        self.assert_one_problem(self.rule("check_links")(self.tree), "live-debt.md", "live-debt")

    def test_debt_citing_a_gap_decision_that_names_it_passes(self):
        self.put(LIVE_DEBT, LIVE_LINKED)
        self.put(GAP_RULE, "# Gap rule\n\n## Known gaps\n\nDebts:\n- `live-debt` %s.\n" % GLOSS)
        self.have(LIVE_DEBT, GAP_RULE)
        self.assertEqual(self.rule("check_links")(self.tree), [])

    def test_debt_citing_a_decision_with_no_gap_section_passes(self):
        self.put(PLAIN_RULE, "# Plain rule\n\nNo gap section here.\n")
        self.put(LINKED_DEBT, "# Linked debt\n\n**Decision.** `plain-rule` %s.\n" % GLOSS)
        self.have(PLAIN_RULE, LINKED_DEBT)
        self.assertEqual(self.rule("check_links")(self.tree), [])

    def test_links_empty_records_pass(self):
        self.assertFalse(os.path.isdir(os.path.join(self.tree, "docs")))  # scope: the tree holds no records
        self.assertEqual(self.rule("check_links")(self.tree), [])

    def test_real_tree_passes_gloss_and_link_rules(self):
        problems = self.rule("check_gloss")(REPO) + self.rule("check_links")(REPO)
        self.assertEqual(problems, [], "%d problems on the real tree, first three: %s" % (len(problems), problems[:3]))


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
