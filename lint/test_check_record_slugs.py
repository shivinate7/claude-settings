#!/usr/bin/env python3
"""Cases for lint/check_record_slugs.py. Standard library only.

    python3 lint/test_check_record_slugs.py

A record file that a change adds must have a slug of 32 characters or fewer. The check reads
decisions/ and debts/ from the diff, or the files it is given.

`--tree [--root R]` reads the decision and debt folders, CLAUDE.md and output-styles/*.md, and prints
each finding as `path:line CODE id`. Its cases are the tree-mode cases at the end of RecordSlugsTests.

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
import layout  # noqa: E402  the record folders come from here, never from a literal (lint/layout.py)
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


# Tree mode (`--tree [--root R]`): a finding is `path:line CODE id`. Parsed from the end of each line, so a
# prefix on the line does not hide the finding.
TREE_FINDING = re.compile(r"(\S+:\d+ (?:GLOSS|DEBT)\d{3} \S+)$")


def tree_found(out):
    """The findings of a tree-mode run, sorted."""
    return sorted(m.group(1) for m in (TREE_FINDING.search(line) for line in out.splitlines()) if m)


def line_of(text, needle):
    """The 1-based line of the first line of `text` that holds `needle`. An expected finding names its real line."""
    return next(i for i, line in enumerate(text.splitlines(), 1) if needle in line)


def commit_all(root):
    """Commit everything under `root`, so a listing by git and a walk of the disk read the same files."""
    for args in (("init", "-q"), ("add", "-A"),
                 ("-c", "user.name=test", "-c", "user.email=test@example.com",
                  "commit", "-q", "--allow-empty", "-m", "fixture")):
        subprocess.run(["git", "-C", root, *args], check=True, capture_output=True, text=True)


class RecordSlugsTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(os.path.isfile(MODULE), "module absent: lint/check_record_slugs.py")
        self.tree = tempfile.mkdtemp(prefix="rsl_", dir=RUN_FOLDER)
        self.addCleanup(tracked_tree.rm_tree, self.tree)
        tracked_tree.copy_tracked(self.tree, "lint", "hooks")  # the layout and the check's imports
        shutil.copyfile(MODULE, os.path.join(self.tree, "lint", "check_record_slugs.py"))

    def put(self, rel, text="# Record\n", root=None):
        path = os.path.join(root or self.tree, *rel.split("/"))
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

    # Tree mode helpers. A record path comes from lint/layout.py, so a folder that moves moves the expected paths too.

    def rel(self, kind, name):
        """A file in the record folder `kind` of the temp tree, as the layout names that folder."""
        return layout.path(self.tree, kind) + "/" + name

    def decision(self, slug, text=None):
        self.put(self.rel("decisions", slug + ".md"), text or "# %s\n" % slug)

    def bare_cite(self, slug="tap-lag", name="other.md"):
        """Write a decision that cites `slug` with no gloss, and return the finding that cite gives."""
        path = self.rel("decisions", name)
        text = "# Other\n\nRule `%s` holds the text.\n" % slug
        self.put(path, text)
        return "%s:%d GLOSS001 %s" % (path, line_of(text, "`%s`" % slug), slug)

    def tree_run(self, root=None):
        """(rc, findings, out) of `--tree` over `root`, the temp tree by default."""
        root = root or self.tree
        commit_all(root)
        rc, out = self.lint("--tree", "--root", root)
        return rc, tree_found(out), out

    def assert_tree(self, want, root=None):
        """The findings are exactly `want`, and the exit code is 1 with a finding, 0 when clean. Each case holds a
        positive finding in `want`, so a run that reports nothing fails on that one, by name."""
        rc, got, out = self.tree_run(root)
        self.assertEqual(got, sorted(want), "tree findings differ: missing %s, unexpected %s"
                         % (sorted(set(want) - set(got)), sorted(set(got) - set(want))))
        self.assertEqual(rc, 1 if want else 0, out)

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

    # Tree mode: `--tree [--root R]` reads each file of the decision and debt folders, CLAUDE.md and output-styles/*.md.
    # Each case pins one finding, or one place the check must stay silent. Each holds a positive finding.

    def test_bare_first_cite_is_gloss001(self):
        # A bare cite of a decision slug is GLOSS001. The tree has no CLAUDE.md and no output-styles/.
        self.decision("tap-lag")
        self.assert_tree([self.bare_cite()])

    def test_one_word_after_a_separator_is_not_a_gloss(self):
        # A gloss has two words or more. Each file's first cite is judged, so four files give four findings.
        self.decision("tap-lag")
        want = []
        for name, form in (("paren", "`tap-lag` (one)"), ("comma", "`tap-lag`, one"),
                           ("colon", "`tap-lag`: one"), ("dash", "`tap-lag` — one")):
            path = self.rel("decisions", name + ".md")
            text = "# %s\n\n%s\n" % (name, form)
            self.put(path, text)
            want.append("%s:%d GLOSS001 tap-lag" % (path, line_of(text, "`tap-lag`")))
        self.assert_tree(want)

    def test_each_gloss_form_passes(self):
        self.decision("tap-lag")
        forms = {
            "paren": "Rule `tap-lag` (two words)",
            "comma": "Rule `tap-lag`, two words",
            "colon": "Rule `tap-lag`: two words",
            "dash": "Rule `tap-lag` — two words",
            "after-words": "Two words (`tap-lag`)",
            "lead": "Two words, `tap-lag`",
        }
        for name, line in forms.items():
            self.put(self.rel("decisions", name + ".md"), "# %s\n\n%s\n" % (name, line))
        self.assert_tree([self.bare_cite(name="bare.md")])  # the positive: the same cite with no gloss

    def test_only_the_first_cite_in_a_file_is_judged(self):
        self.decision("tap-lag")
        self.put(self.rel("decisions", "glossed-first.md"),
                 "# G\n\nRule `tap-lag` (two words) first.\n\nThen Rule `tap-lag` holds the text.\n")
        twice = self.rel("decisions", "bare-twice.md")
        text = "# T\n\nRule `tap-lag` holds.\n\nRule `tap-lag` holds again.\n"
        self.put(twice, text)
        self.assert_tree(["%s:%d GLOSS001 tap-lag" % (twice, line_of(text, "`tap-lag`"))])

    def test_a_cite_in_a_fenced_block_is_not_a_cite(self):
        self.decision("tap-lag")
        path = self.rel("decisions", "fenced.md")
        text = "# F\n\n```\nRule `tap-lag` holds.\n```\n\nRule `tap-lag` holds the text.\n"
        self.put(path, text)
        self.assert_tree(["%s:%d GLOSS001 tap-lag" % (path, line_of(text, "holds the text"))])

    def test_a_cite_in_an_html_comment_is_not_a_cite(self):
        self.decision("tap-lag")
        path = self.rel("decisions", "commented.md")
        text = ("# C\n\n<!-- see `tap-lag` here -->\n\n<!--\nRule `tap-lag` holds.\n-->\n\n"
                "Rule `tap-lag` holds the text.\n")
        self.put(path, text)
        self.assert_tree(["%s:%d GLOSS001 tap-lag" % (path, line_of(text, "holds the text"))])

    def test_a_span_that_is_not_exactly_an_id_is_not_a_cite(self):
        self.decision("tap-lag")
        path = self.rel("decisions", "flag-span.md")
        text = "# S\n\nRun `tap-lag --flag` first.\n\nRule `tap-lag` holds the text.\n"
        self.put(path, text)
        self.assert_tree(["%s:%d GLOSS001 tap-lag" % (path, line_of(text, "holds the text"))])

    def test_a_file_citing_its_own_slug_is_not_a_finding(self):
        self.decision("tap-lag", "# Tap lag\n\nRule `tap-lag` holds the text.\n")
        self.assert_tree([self.bare_cite()])  # the positive: another file's bare cite of the same slug

    def test_a_comment_opener_in_a_span_does_not_hide_a_cite(self):
        # The openers are `/*`, `//` and `#`, each in a span before the cite on the same line.
        for slug in ("a-one", "a-two", "a-three"):
            self.decision(slug)
        path = self.rel("decisions", "openers.md")
        text = ("# O\n\nThe `/*` span, then Rule `a-one` holds.\n"
                "The `//` span, then Rule `a-two` holds.\n"
                "The `#` span, then Rule `a-three` holds.\n")
        self.put(path, text)
        self.assert_tree(["%s:%d GLOSS001 %s" % (path, line_of(text, slug), slug)
                          for slug in ("a-one", "a-two", "a-three")])

    def test_a_multi_line_span_before_a_cite_does_not_hide_it(self):
        self.decision("a-four")
        path = self.rel("decisions", "span.md")
        text = "# S\n\nThe `// first\nsecond` span, then Rule `a-four` holds.\n"
        self.put(path, text)
        self.assert_tree(["%s:%d GLOSS001 a-four" % (path, line_of(text, "a-four"))])

    def test_a_lone_quote_in_text_does_not_hide_a_cite(self):
        # Don't, and <p>Don't</p>, each put a lone quote before a cite on its line. The last cite is glossed.
        for slug in ("a-five", "a-six", "a-seven"):
            self.decision(slug)
        path = self.rel("decisions", "quote.md")
        text = ("# Q\n\nDon't use Rule `a-five` holds.\n\n"
                "<p>Don't</p> Rule `a-seven` holds.\n\n"
                "Don't do `a-six` (two words) here.\n")
        self.put(path, text)
        self.assert_tree(["%s:%d GLOSS001 a-five" % (path, line_of(text, "a-five")),
                          "%s:%d GLOSS001 a-seven" % (path, line_of(text, "a-seven"))])

    def test_claude_md_and_output_styles_are_scanned(self):
        self.decision("tap-lag")
        self.put("CLAUDE.md", "# Rules\n\nRule `tap-lag` holds.\n")
        self.put("output-styles/style.md", "# Style\n\nRule `tap-lag` holds.\n")
        self.assert_tree(["CLAUDE.md:3 GLOSS001 tap-lag", "output-styles/style.md:3 GLOSS001 tap-lag"])

    def test_rule_anchors_in_claude_md_and_output_styles_are_ids(self):
        self.put("CLAUDE.md", "Rule text.<!-- rule:route-x -->\n")
        self.put("output-styles/style.md", "Rule text.<!-- rule:style-y -->\n")
        other = self.rel("decisions", "other.md")
        text = "# Other\n\nRule `route-x` holds the text.\n\nRule `style-y` holds the text.\n"
        self.put(other, text)
        self.assert_tree(["%s:%d GLOSS001 route-x" % (other, line_of(text, "route-x")),
                          "%s:%d GLOSS001 style-y" % (other, line_of(text, "style-y"))])

    def test_a_plan_slug_is_an_id_and_plan_text_is_not_scanned(self):
        self.decision("tap-lag")
        self.put(self.rel("plans", "plan-z.md"), "# Plan\n\nRule `tap-lag` holds.\n")
        self.assert_tree([self.bare_cite("plan-z")])

    def test_a_debt_slug_is_an_id(self):
        # The decision names the debt in a glossed cite, so the debt raises no DEBT finding.
        self.decision("tap-lag", "# Tap lag\n\nThe debt `debt-q` (its finding) waits.\n")
        self.put(self.rel("debts", "debt-q.md"), "# Debt\n\n**Decision.** `tap-lag` (a valid gloss).\n")
        self.assert_tree([self.bare_cite("debt-q")])

    def test_an_anchor_outside_the_id_sources_is_not_an_id(self):
        self.decision("tap-lag")
        self.put(self.rel("decisions", "zz.md"), "# Z\n\n<!-- rule:ghost-r -->\n")
        other = self.rel("decisions", "other.md")
        text = "# Other\n\nRule `ghost-r` holds the text.\n\nRule `not-an-id` holds.\n\nRule `tap-lag` holds.\n"
        self.put(other, text)
        self.assert_tree(["%s:%d GLOSS001 tap-lag" % (other, line_of(text, "`tap-lag`"))])

    def test_records_index_catalog_and_debt_notes_and_readme_are_not_scanned(self):
        # The tree has no CLAUDE.md and no output-styles/, so the empty states are covered here as well.
        self.decision("tap-lag")
        for path in ("docs/records.md", "docs/catalog.md", self.rel("debts", "README.md"),
                     layout.path(self.tree, "debt-notes")):
            self.put(path, "# Skipped\n\nRule `tap-lag` holds.\n")
        self.assert_tree([self.bare_cite()])

    def test_a_debt_file_is_scanned_for_gloss(self):
        self.decision("a-eight")
        debt = self.rel("debts", "debt-r.md")
        text = "# Debt\n\nRule `a-eight` holds the text.\n\n**Decision.** none\n"
        self.put(debt, text)
        self.assert_tree(["%s:%d GLOSS001 a-eight" % (debt, line_of(text, "a-eight"))])

    def test_the_record_folders_come_from_the_layout(self):
        # A repo rolled out to the layout keeps its records under docs/. Its legacy folders are then not records.
        # The docs/ names below are the rolled-out places themselves, so they stay literal.
        self.put(".claude/layout-extras.json", '{"rolled-out": true, "kinds": {}}\n')
        self.put("docs/decisions/tap-lag.md", "# Tap lag\n")
        moved = "docs/decisions/other.md"
        text = "# Other\n\nRule `tap-lag` holds the text.\n"
        self.put(moved, text)
        self.put("decisions/old.md", "# Old\n\nRule `tap-lag` holds the text.\n")
        self.put("docs/debts/d-ten.md", "# Debt\n")
        self.assert_tree(["%s:%d GLOSS001 tap-lag" % (moved, line_of(text, "`tap-lag`")),
                          "docs/debts/d-ten.md:1 DEBT001 d-ten"])

    def test_root_names_the_tree_read_not_the_working_directory(self):
        # The working tree holds its own finding. With --root, only the named tree's finding is reported.
        self.decision("tap-lag")
        self.put(self.rel("decisions", "own.md"), "# Own\n\nRule `tap-lag` holds the text.\n")
        root = tempfile.mkdtemp(prefix="rsl_root_", dir=RUN_FOLDER)
        self.addCleanup(tracked_tree.rm_tree, root)
        self.put(layout.path(root, "decisions") + "/tap-lag.md", "# Tap lag\n", root=root)
        other = layout.path(root, "decisions") + "/other.md"
        text = "# Other\n\nRule `tap-lag` holds the text.\n"
        self.put(other, text, root=root)
        self.assert_tree(["%s:%d GLOSS001 tap-lag" % (other, line_of(text, "`tap-lag`"))], root=root)

    def test_exit_is_one_with_a_finding_and_zero_once_it_is_gone(self):
        self.decision("tap-lag")
        other = self.rel("decisions", "other.md")
        text = "# Other\n\nRule `tap-lag` holds the text.\n"
        self.put(other, text)
        self.assert_tree(["%s:%d GLOSS001 tap-lag" % (other, line_of(text, "`tap-lag`"))])
        os.remove(os.path.join(self.tree, *other.split("/")))
        self.assert_tree([])  # rc 0 and no finding

    def test_a_debt_with_no_decision_line_is_debt001(self):
        path = self.rel("debts", "d-one.md")
        self.put(path, "# Debt\n\nWhat: a gap.\n")
        self.assert_tree(["%s:1 DEBT001 d-one" % path])  # no line holds the part, so the finding names line 1

    def test_a_bullet_decision_line_counts(self):
        self.decision("tap-lag", "# Tap lag\n\nThe debt `d-two` (its finding) waits.\n")
        self.put(self.rel("debts", "d-two.md"), "# Debt\n\n- **Decision.** `tap-lag` (a valid gloss)\n")
        path = self.rel("debts", "d-one.md")
        self.put(path, "# Debt\n\nWhat: a gap.\n")  # the positive: no decision line
        self.assert_tree(["%s:1 DEBT001 d-one" % path])

    def test_a_marker_mid_line_is_not_a_decision_line(self):
        self.decision("tap-lag")
        path = self.rel("debts", "d-three.md")
        self.put(path, "# Debt\n\nSee the line **Decision.** `tap-lag` (a valid gloss).\n")
        self.assert_tree(["%s:1 DEBT001 d-three" % path])

    def test_a_decision_line_naming_no_decision_is_debt002(self):
        path = self.rel("debts", "d-four.md")
        text = "# Debt\n\n**Decision.** `ghost-decision` (a missing decision)\n"
        self.put(path, text)
        self.assert_tree(["%s:%d DEBT002 ghost-decision" % (path, line_of(text, "**Decision.**"))])

    def test_none_and_none_with_a_period_are_accepted(self):
        self.put(self.rel("debts", "d-five.md"), "# Debt\n\n**Decision.** none\n")
        self.put(self.rel("debts", "d-six.md"), "# Debt\n\n- **Decision.** none.\n")
        path = self.rel("debts", "d-four.md")  # the positive: a ghost slug
        text = "# Debt\n\n**Decision.** `ghost-decision` (a missing decision)\n"
        self.put(path, text)
        self.assert_tree(["%s:%d DEBT002 ghost-decision" % (path, line_of(text, "**Decision.**"))])

    def test_a_backticked_none_is_none_but_a_sentence_is_not(self):
        # A backticked none is none. A line that starts with none and goes on names no decision, so it is DEBT002.
        self.put(self.rel("debts", "d-bt1.md"), "# Debt\n\n**Decision.** `none`\n")
        self.put(self.rel("debts", "d-bt2.md"), "# Debt\n\n**Decision.** `none`.\n")
        path = self.rel("debts", "d-bt3.md")
        text = "# Debt\n\n**Decision.** none on main, see x\n"
        self.put(path, text)
        self.assert_tree(["%s:%d DEBT002 none" % (path, line_of(text, "**Decision.**"))])

    def test_a_bare_cite_of_a_decision_on_a_debt_is_gloss001_and_a_gloss_clears_it(self):
        # Both debts cite tap-lag on their Decision line. Only the bare cite is a finding.
        self.decision("tap-lag", "# Tap lag\n\nThe debt `d-bare` (its finding) waits.\n"
                                 "The debt `d-glossed` (its finding) waits.\n")
        bare = self.rel("debts", "d-bare.md")
        text = "# Debt\n\n**Decision.** `tap-lag`\n"
        self.put(bare, text)
        self.put(self.rel("debts", "d-glossed.md"), "# Debt\n\n**Decision.** `tap-lag` (tap feels slow)\n")
        self.assert_tree(["%s:%d GLOSS001 tap-lag" % (bare, line_of(text, "**Decision.**"))])

    def test_a_plain_whole_word_names_a_debt_and_a_longer_word_does_not(self):
        # tap-two names d1x in plain text as a whole word, so debt d1x is named. It holds d1 only inside d1x.
        # Its cite of d1x has a gloss, so the bare-cite rule leaves only the DEBT003 finding.
        self.decision("tap-two", "# Tap two\n\n- d1x: two words open\n")
        self.put(self.rel("debts", "d1x.md"), "# Debt\n\n**Decision.** `tap-two` (a valid gloss)\n")
        d1 = self.rel("debts", "d1.md")
        text = "# Debt\n\n**Decision.** `tap-two` (a valid gloss)\n"
        self.put(d1, text)
        self.assert_tree(["%s:%d DEBT003 d1" % (d1, line_of(text, "**Decision.**"))])

    def test_an_unbackticked_decision_slug_is_gloss001_and_a_gloss_clears_it(self):
        # The Decision line names tap-lag with no backticks. Bare, with or without a period, it is a cite: GLOSS001.
        # With a gloss it is clean. The decision names the three debts in glossed cites, so no DEBT finding.
        self.decision("tap-lag", "# Tap lag\n\nThe debt `d-plain` (its finding) waits.\n"
                                 "The debt `d-period` (its finding) waits.\n"
                                 "The debt `d-gloss` (its finding) waits.\n")
        plain = self.rel("debts", "d-plain.md")
        text = "# Debt\n\n- **Decision.** tap-lag\n"
        self.put(plain, text)
        period = self.rel("debts", "d-period.md")
        period_text = "# Debt\n\n- **Decision.** tap-lag.\n"
        self.put(period, period_text)
        self.put(self.rel("debts", "d-gloss.md"), "# Debt\n\n- **Decision.** tap-lag (tap feels slow).\n")
        self.assert_tree([
            "%s:%d GLOSS001 tap-lag" % (plain, line_of(text, "**Decision.**")),
            "%s:%d GLOSS001 tap-lag" % (period, line_of(period_text, "**Decision.**")),
        ])

    def test_a_named_decision_must_name_the_debt(self):
        # tap-lag names d-eight but not d-seven, so d-seven's decision line fails DEBT003.
        self.decision("tap-lag", "# Tap lag\n\nThe debt `d-eight` (its finding) waits.\n")
        seven = self.rel("debts", "d-seven.md")
        self.put(seven, "# Debt\n\n**Decision.** `tap-lag` (a valid gloss)\n")
        self.put(self.rel("debts", "d-eight.md"), "# Debt\n\n**Decision.** `tap-lag` (a valid gloss)\n")
        self.assert_tree(["%s:3 DEBT003 d-seven" % seven])

    def test_none_while_a_decision_names_the_debt_is_debt004(self):
        self.decision("dec-nine", "# Dec\n\nThe debt `d-nine` (its finding) waits.\n")
        path = self.rel("debts", "d-nine.md")
        self.put(path, "# Debt\n\n**Decision.** none\n")
        self.assert_tree(["%s:3 DEBT004 d-nine" % path])

    def test_the_default_and_file_modes_do_not_read_the_gloss_or_debt_rules(self):
        # Only --tree reads the gloss and debt rules. The other modes must not start to.
        self.decision("tap-lag")
        self.put(self.rel("decisions", "other.md"), "# Other\n\nRule `tap-lag` holds the text.\n")
        self.put(self.rel("debts", "d-one.md"), "# Debt\n\nWhat: a gap.\n")
        self.assert_passes(self.rel("decisions", "other.md"), self.rel("debts", "d-one.md"))

    def test_an_unreadable_layout_is_red_in_tree_mode(self):
        self.put("lint/layout.json", "{not json\n")  # the copy that the temp tree's script reads
        rc, out = self.lint("--tree", "--root", self.tree)
        self.assertEqual(rc, 1, out)
        self.assertIn("cannot read", out)  # the same LayoutError the other modes print
        self.assertNotIn("Traceback", out)

    def test_tree_findings_returns_the_findings_the_command_prints(self):
        # getattr: a missing name fails the assert below instead of raising.
        self.decision("tap-lag")
        want = self.bare_cite()
        commit_all(self.tree)
        spec = importlib.util.spec_from_file_location("record_slugs_tree_probe", MODULE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        fn = getattr(module, "tree_findings", None)
        self.assertIsNotNone(fn, "tree_findings(root) is not defined in lint/check_record_slugs.py")
        self.assertEqual(sorted(fn(self.tree)), [want])

    # Bare cites (speak-cite-id-plus-gloss): a record id written as a whole word in prose is a cite, as a backticked
    # span is. The gloss window is the paragraph. Each case holds a positive finding, so a silent run fails.

    def test_a_bare_prose_cite_with_no_gloss_is_gloss001(self):
        self.decision("session-tiers")
        path = self.rel("decisions", "other.md")
        text = "# Other\n\nSee session-tiers for more.\n\nSee session-tiers again.\n"  # only the first cite is judged
        self.put(path, text)
        self.assert_tree(["%s:%d GLOSS001 session-tiers" % (path, line_of(text, "session-tiers"))])

    def test_a_bare_prose_cite_with_a_gloss_passes(self):
        self.decision("session-tiers")
        self.put(self.rel("decisions", "glossed.md"), "# Glossed\n\nSee session-tiers (the session shapes).\n")
        path = self.rel("decisions", "bare.md")  # the positive: the same cite with no gloss
        text = "# Bare\n\nSee session-tiers for more.\n"
        self.put(path, text)
        self.assert_tree(["%s:%d GLOSS001 session-tiers" % (path, line_of(text, "session-tiers"))])

    def test_a_lone_quote_does_not_hide_a_bare_cite(self):
        # Don't, and <p>Don't</p>, each put a lone quote before a bare cite on its line.
        self.decision("session-tiers")
        first = self.rel("decisions", "quote-one.md")
        first_text = "# Q\n\nDon't see session-tiers for more.\n"
        second = self.rel("decisions", "quote-two.md")
        second_text = "# Q\n\n<p>Don't</p> See session-tiers for more.\n"
        self.put(first, first_text)
        self.put(second, second_text)
        self.assert_tree(["%s:%d GLOSS001 session-tiers" % (first, line_of(first_text, "session-tiers")),
                          "%s:%d GLOSS001 session-tiers" % (second, line_of(second_text, "session-tiers"))])

    def test_a_comment_opener_in_a_span_does_not_hide_a_bare_cite(self):
        # The span holds an HTML comment opener, and a real comment follows it. The cite between them still counts.
        self.decision("session-tiers")
        path = self.rel("decisions", "opener.md")
        text = "# O\n\nWrite `<!--` then see session-tiers for more.\n\n<!-- a note -->\n"
        self.put(path, text)
        self.assert_tree(["%s:%d GLOSS001 session-tiers" % (path, line_of(text, "session-tiers"))])

    def test_a_bare_id_in_a_span_fence_or_comment_is_not_a_cite(self):
        self.decision("session-tiers")
        self.put(self.rel("decisions", "skipped.md"),
                 "# S\n\nRun `open session-tiers` first.\n\n```\nSee session-tiers for more.\n```\n\n"
                 "<!-- See session-tiers for more. -->\n")
        path = self.rel("decisions", "other.md")  # the positive: a bare cite outside all three
        text = "# Other\n\nSee session-tiers for more.\n"
        self.put(path, text)
        self.assert_tree(["%s:%d GLOSS001 session-tiers" % (path, line_of(text, "session-tiers"))])

    def test_a_bare_id_in_a_link_target_is_not_a_cite(self):
        self.decision("session-tiers")
        self.put(self.rel("decisions", "linked.md"),
                 "# L\n\nRead [the tiers](../decisions/session-tiers.md) (the session shapes) first.\n")
        path = self.rel("decisions", "other.md")  # the positive: a bare cite outside the link target
        text = "# Other\n\nSee session-tiers for more.\n"
        self.put(path, text)
        self.assert_tree(["%s:%d GLOSS001 session-tiers" % (path, line_of(text, "session-tiers"))])

    def test_a_bare_id_in_a_url_is_not_a_cite(self):
        self.decision("session-tiers")
        self.put(self.rel("decisions", "linked.md"), "# L\n\nSee https://example.com/session-tiers for more.\n")
        path = self.rel("decisions", "other.md")  # the positive: a bare cite outside the URL
        text = "# Other\n\nSee session-tiers for more.\n"
        self.put(path, text)
        self.assert_tree(["%s:%d GLOSS001 session-tiers" % (path, line_of(text, "session-tiers"))])

    def test_a_bare_id_inside_a_longer_slug_is_not_a_cite(self):
        # d1 is not a cite inside d1-two: a hyphen or a word character bounds a whole word.
        self.decision("d1")
        self.decision("d1-two")
        path = self.rel("decisions", "other.md")
        text = "# Other\n\nRule d1-two holds the text.\n"
        self.put(path, text)
        self.assert_tree(["%s:%d GLOSS001 d1-two" % (path, line_of(text, "d1-two"))])

    def test_a_files_own_slug_in_prose_is_not_a_cite(self):
        self.decision("session-tiers", "# Session tiers\n\nSee session-tiers for more.\n")
        path = self.rel("decisions", "other.md")  # the positive: another file's bare cite of the same slug
        text = "# Other\n\nSee session-tiers for more.\n"
        self.put(path, text)
        self.assert_tree(["%s:%d GLOSS001 session-tiers" % (path, line_of(text, "session-tiers"))])

    def test_a_glossed_backticked_first_cite_then_a_bare_later_cite_is_not_flagged(self):
        self.decision("session-tiers")
        self.put(self.rel("decisions", "first.md"),
                 "# F\n\nRule `session-tiers` (two words) holds.\n\nLater, session-tiers holds too.\n")
        path = self.rel("decisions", "other.md")  # the positive: a bare first cite is judged
        text = "# Other\n\nSee session-tiers for more.\n"
        self.put(path, text)
        self.assert_tree(["%s:%d GLOSS001 session-tiers" % (path, line_of(text, "session-tiers"))])

    def test_a_bare_first_cite_is_judged_before_a_backticked_later_cite(self):
        self.decision("session-tiers")
        path = self.rel("decisions", "mixed.md")
        text = "# M\n\nSee session-tiers for more.\n\nRule `session-tiers` holds the text.\n"
        self.put(path, text)
        self.assert_tree(["%s:%d GLOSS001 session-tiers" % (path, line_of(text, "See session-tiers"))])

    def test_a_gloss_on_the_next_line_of_the_same_paragraph_passes(self):
        # A cite at a line end takes a gloss that starts on the next line of its paragraph, bare or backticked.
        self.decision("tap-lag")
        self.decision("session-tiers")
        self.put(self.rel("decisions", "wrapped.md"), "# W\n\nSee `tap-lag`\n(two words) here.\n")
        self.put(self.rel("decisions", "wrapped-bare.md"), "# W\n\nSee session-tiers\n(two words) here.\n")
        path = self.rel("decisions", "other.md")  # the positive: a bare cite with no gloss on any line
        text = "# Other\n\nSee session-tiers for more.\n"
        self.put(path, text)
        self.assert_tree(["%s:%d GLOSS001 session-tiers" % (path, line_of(text, "session-tiers"))])

    def test_a_cite_at_a_paragraph_end_takes_no_gloss_from_the_next_paragraph(self):
        self.decision("tap-lag")
        plain = self.rel("decisions", "plain.md")
        plain_text = "# P\n\nSee `tap-lag`\n\nTwo words here.\n"
        paren = self.rel("decisions", "paren.md")
        paren_text = "# P\n\nSee `tap-lag`\n\n(two words) here.\n"
        self.put(plain, plain_text)
        self.put(paren, paren_text)
        self.assert_tree(["%s:%d GLOSS001 tap-lag" % (plain, line_of(plain_text, "`tap-lag`")),
                          "%s:%d GLOSS001 tap-lag" % (paren, line_of(paren_text, "`tap-lag`"))])

    def test_a_cite_at_a_list_item_end_takes_no_gloss_from_the_next_item(self):
        self.decision("tap-lag")
        path = self.rel("decisions", "items.md")
        text = "# I\n\n- `tap-lag`\n- two words here\n"
        self.put(path, text)
        self.assert_tree(["%s:%d GLOSS001 tap-lag" % (path, line_of(text, "`tap-lag`"))])

    def test_a_gloss_from_the_previous_paragraph_does_not_count(self):
        self.decision("tap-lag")
        path = self.rel("decisions", "prev.md")
        text = "# P\n\nTwo words,\n\n`tap-lag` holds the text.\n"
        self.put(path, text)
        self.assert_tree(["%s:%d GLOSS001 tap-lag" % (path, line_of(text, "`tap-lag`"))])

    def test_a_bare_anchor_in_claude_md_prose_is_a_cite(self):
        # The anchor's own comment is not a cite, so the prose cite on line 3 is the first one.
        self.put("CLAUDE.md", "Rule text.<!-- rule:route-x -->\n\nSee route-x for more.\n")
        self.assert_tree(["CLAUDE.md:3 GLOSS001 route-x"])

    def test_a_bare_id_in_a_debts_prose_is_a_cite(self):
        self.decision("tap-lag", "# Tap lag\n\nThe debt `d-x` (its finding) waits.\n")
        self.decision("session-tiers")
        path = self.rel("debts", "d-x.md")
        text = "# Debt\n\n**Decision.** `tap-lag` (a valid gloss)\n\nWhat: waits on session-tiers.\n"
        self.put(path, text)
        self.assert_tree(["%s:%d GLOSS001 session-tiers" % (path, line_of(text, "session-tiers"))])


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
