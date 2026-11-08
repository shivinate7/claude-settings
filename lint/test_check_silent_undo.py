#!/usr/bin/env python3
"""Fixture suite for lint/check_silent_undo.py. Run: python3 lint/test_check_silent_undo.py

Every case builds a throwaway repo with a local `origin` and asks the check for a verdict.
Red cases: a squash that carries the pre-deletion copy of a file (a revert nobody wrote), and a
merge that drops a parent's added line.
"""
import atexit, contextlib, inspect, io, json, os, re, shutil, subprocess, sys, tempfile, unittest, unittest.mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: the run folder's one home (lint/_test_temp.py)
import check_debt_retire as D  # noqa: E402  the debt-close check: the scope each Retire-run case is read against
from test_check_debt_retire import PROSE, RUN_URL, Runs, debt  # noqa: E402  one home of the debt shape and the fake run reader
sys.path.insert(0, os.path.join(HERE, "..", "merge"))
import check_silent_undo as C  # noqa: E402
from workflow_steps import job_block, run_body, step_blocks, step_env, step_key  # noqa: E402  the one home of the step parser
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import tracked_tree  # noqa: E402  copies what git lists, so no fixture lists files (testing/tracked_tree.py)

RUN = os.path.realpath(_test_temp.run_folder())  # every temp repo of this run lives under it, removed at exit
atexit.register(shutil.rmtree, RUN, True)

ENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull, GIT_AUTHOR_NAME="t",
           GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
os.environ.update({k: ENV[k] for k in ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL")})

BODY = "".join("line %d\n" % i for i in range(1, 21))


REPOS = []


def tearDownModule():
    for r in REPOS:
        r.tmp.cleanup()


OPT_OUT_KEYS = ("GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")


def without_opt_out(env):
    """`env` without the test-run signing opt-out (lint/_test_git.py). Only a case that signs on purpose uses it."""
    return {k: v for k, v in env.items() if not k.startswith(OPT_OUT_KEYS)}


class Repo:
    def __init__(self):
        self.signs = False  # a case that signs on purpose sets this, and its git runs without the opt-out
        self.tmp = tempfile.TemporaryDirectory(dir=RUN)
        REPOS.append(self)
        self.dir = os.path.join(self.tmp.name, "w")
        origin = os.path.join(self.tmp.name, "o.git")
        self.sh("init", "-q", "--bare", origin, cwd=self.tmp.name)
        self.sh("init", "-q", "-b", "main", self.dir, cwd=self.tmp.name)
        self.sh("remote", "add", "origin", origin)

    def sh(self, *a, cwd=None, ok=True, date=None):
        env = dict(os.environ, GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date) if date else None
        if self.signs:
            env = without_opt_out(env or os.environ)
        r = subprocess.run(["git", *a], cwd=cwd or self.dir, capture_output=True, text=True, env=env)
        assert r.returncode == 0 or not ok, (a, r.stdout, r.stderr)
        return r.stdout.strip()

    def put(self, path, text):
        full = os.path.join(self.dir, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as f:
            f.write(text)

    def commit(self, msg, date=None, **files):
        for k, v in files.items():
            self.put(k.replace("__", "/").replace("_md", ".md").replace("_txt", ".txt"), v)
        self.sh("add", "-A")
        self.sh("commit", "-q", "-m", msg, date=date)
        return self.sh("rev-parse", "HEAD")

    def push(self):
        self.sh("push", "-q", "origin", "main")
        self.sh("fetch", "-q", "origin")

    def verdict(self, head="HEAD"):
        got, self.notes = C.check(self.dir, "origin/main", head)
        return got


def base_repo():
    r = Repo()
    r.put("app.txt", BODY + "function Card() {}\n")
    r.put("other.txt", "other v1\n")
    r.commit("base")
    r.push()
    return r


class Red(unittest.TestCase):
    def setUp(self):
        self.r = base_repo()

    def merged_pr(self, branch="pr1", msg="delete Card", **files):
        """PR 1: deletes Card from app.txt, merges into main with a merge commit. `files` replaces that edit."""
        r = self.r
        r.sh("checkout", "-q", "-b", branch)
        r.commit(msg, **(files or {"app_txt": BODY}))
        r.sh("checkout", "-q", "main")
        r.sh("merge", "-q", "--no-ff", "-m", "Merge pull request #1", branch)
        r.push()

    def test_revert_of_a_prior_pr(self):
        self.merged_pr()
        r = self.r
        r.sh("checkout", "-q", "-b", "oops")
        r.commit("tidy other", other_txt="other v2\n")
        r.sh("revert", "--no-edit", "-m", "1", "main")
        got = r.verdict()
        self.assertTrue(any("app.txt" in p and "undoing" in p for p in got), got)

    def test_revert_with_trailer_passes(self):
        self.merged_pr()
        r = self.r
        r.sh("checkout", "-q", "-b", "oops")
        r.sh("revert", "--no-edit", "-m", "1", "main")
        r.sh("commit", "-q", "--amend", "-m", "Bring Card back\n\nDrops-lines: app.txt -- the owner wants Card back")
        self.assertEqual(r.verdict(), [])
        self.assertEqual(r.notes, ["ALLOWED app.txt: the owner wants Card back"])

    def test_stale_branch_keep_ours_merge(self):
        """banchi shape: cut before the PR, merge main keeping ours, land: the old file returns."""
        r = self.r
        r.sh("checkout", "-q", "-b", "stale")
        r.sh("checkout", "-q", "main")
        self.merged_pr("pr1")
        r.sh("checkout", "-q", "stale")
        r.commit("wording", other_txt="other v2\n")
        r.sh("merge", "-q", "-s", "ours", "--no-edit", "main")
        got = r.verdict()
        self.assertTrue(any("app.txt" in p and "whole file restored" in p for p in got), got)

    def test_stale_merge_whose_first_commit_postdates_the_pr_is_read(self):
        """The banchi shape with the clock pinned. The branch is cut before the PR merges, and its
        first commit lands about an hour after the merge. The window starts where the branch's own
        first-parent line left main, so the PR is in it and the restore is read. The dates do not set
        the window. Fixed dates pin that gap on every run."""
        r = self.r
        r.sh("checkout", "-q", "-b", "stale")
        r.sh("checkout", "-q", "main")
        r.sh("checkout", "-q", "-b", "pr1")
        r.commit("delete Card", date="2026-01-01T10:00:00", app_txt=BODY)
        r.sh("checkout", "-q", "main")
        r.sh("merge", "-q", "--no-ff", "-m", "Merge pull request #1", "pr1", date="2026-01-01T10:01:00")
        r.push()
        r.sh("checkout", "-q", "stale")
        r.commit("wording", date="2026-01-01T11:00:00", other_txt="other v2\n")
        r.sh("merge", "-q", "-s", "ours", "--no-edit", "main", date="2026-01-01T11:01:00")
        got = r.verdict()
        self.assertTrue(any("app.txt" in p and "whole file restored" in p for p in got), got)

    def test_stale_branch_hunk_level(self):
        """Main added a comment after the PR; the branch restores Card but keeps the comment."""
        self.merged_pr()
        r = self.r
        r.sh("checkout", "-q", "-b", "silent")
        r.commit("wording", app_txt=BODY + "function Card() {}\n")
        got = r.verdict()
        self.assertTrue(any("app.txt" in p and "undoing" in p for p in got), got)

    def test_conflict_resolved_taking_ours_drops_the_other_side(self):
        r = self.r
        r.sh("checkout", "-q", "-b", "feat")
        r.commit("feat edits line 5", app_txt=BODY.replace("line 5\n", "line 5 feat\n") + "function Card() {}\n")
        r.sh("checkout", "-q", "main")
        r.commit("main edits line 5", app_txt=BODY.replace("line 5\n", "line 5 main\nmain extra\n") + "function Card() {}\n")
        r.push()
        r.sh("checkout", "-q", "feat")
        r.sh("merge", "main", ok=False)  # conflicts
        r.sh("checkout", "--ours", "app.txt")
        r.sh("add", "app.txt")
        r.sh("commit", "-q", "--no-edit")
        got = r.verdict()
        self.assertTrue(any("app.txt" in p and "drops" in p and "main extra" in p for p in got), got)

    def test_hand_drop_in_a_merge_without_conflict(self):
        r = self.r
        r.sh("checkout", "-q", "-b", "feat")
        r.commit("feat", other_txt="other v2\n")
        r.sh("checkout", "-q", "main")
        r.commit("main adds", app_txt=BODY + "function Card() {}\nadded by main\n")
        r.push()
        r.sh("checkout", "-q", "feat")
        r.sh("merge", "--no-commit", "--no-ff", "main")
        r.put("app.txt", BODY + "function Card() {}\n")
        r.sh("add", "-A")
        r.sh("commit", "-q", "-m", "Merge main")
        got = r.verdict()
        self.assertTrue(any("added by main" in p for p in got), got)

    def test_trailer_on_the_merge_allows_the_drop(self):
        r = self.r
        r.sh("checkout", "-q", "-b", "feat")
        r.commit("feat", other_txt="other v2\n")
        r.sh("checkout", "-q", "main")
        r.commit("main adds", app_txt=BODY + "function Card() {}\nadded by main\n")
        r.push()
        r.sh("checkout", "-q", "feat")
        r.sh("merge", "--no-commit", "--no-ff", "main")
        r.put("app.txt", BODY + "function Card() {}\n")
        r.sh("add", "-A")
        r.sh("commit", "-q", "-m", "Merge main\n\nDrops-lines: app.txt -- main's line is dead")
        self.assertEqual(r.verdict(), [])

    def assert_names_a_delete(self, path):
        """The branch deleted `path`, which an earlier PR added: each finding says so, never a restore."""
        got = [p for p in self.r.verdict() if p.startswith(path + ":")]
        self.assertTrue(got, "no finding for %s" % path)
        for p in got:
            self.assertIn("deleted", p)
            self.assertNotIn("restored", p)
            self.assertNotIn("hunk reversed", p)

    def test_a_delete_of_a_file_a_prior_pr_added_says_deleted(self):
        """A file a merged PR added, then deleted on a later branch, reads as deleted."""
        self.merged_pr(msg="add debt", docs__debts__missing_md="debt body line\nsecond line\n")
        r = self.r
        r.sh("checkout", "-q", "-b", "gone")
        r.sh("rm", "-q", "docs/debts/missing.md")
        r.sh("commit", "-q", "-m", "drop the debt")
        self.assert_names_a_delete("docs/debts/missing.md")

    def test_a_delete_of_a_file_a_prior_pr_added_and_main_then_edited_says_deleted(self):
        """The same, with a later main commit that edits the file: the whole-file blob no longer matches."""
        self.merged_pr(msg="add debt", docs__debts__missing_md="debt body line\nsecond line\n")
        r = self.r
        r.commit("main edits the debt", docs__debts__missing_md="debt body line\nsecond line\nthird line\n")
        r.push()
        r.sh("checkout", "-q", "-b", "gone")
        r.sh("rm", "-q", "docs/debts/missing.md")
        r.sh("commit", "-q", "-m", "drop the debt")
        self.assert_names_a_delete("docs/debts/missing.md")


class PrBodyEscape(unittest.TestCase):
    """A `Drops-lines: <path> -- <reason>` line in the PR body excuses its path, as a commit trailer does.
    A line with no reason, or one for another path, excuses nothing. Each use prints ALLOWED."""

    def setUp(self):
        r = self.r = base_repo()
        r.sh("checkout", "-q", "-b", "pr1")
        r.commit("delete Card", app_txt=BODY)
        r.sh("checkout", "-q", "main")
        r.sh("merge", "-q", "--no-ff", "-m", "Merge pull request #1", "pr1")
        r.push()
        r.sh("checkout", "-q", "-b", "oops")
        r.commit("tidy other", other_txt="other v2\n")
        r.sh("revert", "--no-edit", "-m", "1", "main")

    def test_a_pr_body_line_excuses_its_path(self):
        got, notes = C.check(self.r.dir, "origin/main", "HEAD",
                             pr_body="Drops-lines: other.txt -- not this file\nDrops-lines: app.txt -- the owner wants Card back\n")
        self.assertEqual(got, [])
        self.assertEqual(notes, ["ALLOWED app.txt: the owner wants Card back"])

    def test_a_pr_body_line_without_a_reason_excuses_nothing(self):
        for body in ("Drops-lines: app.txt\n", "Drops-lines: app.txt --\n", "Drops-lines: app.txt -- \n"):
            with self.subTest(body=body):
                got, notes = C.check(self.r.dir, "origin/main", "HEAD", pr_body=body)
                self.assertTrue(any("app.txt" in p and "undoing" in p for p in got), got)
                self.assertFalse(any(n.startswith("ALLOWED") for n in notes), notes)

    def test_a_pr_body_line_for_another_path_does_not_excuse(self):
        got, notes = C.check(self.r.dir, "origin/main", "HEAD", pr_body="Drops-lines: other.txt -- wrong file\n")
        self.assertTrue(any("app.txt" in p and "undoing" in p for p in got), got)
        self.assertFalse(any(n.startswith("ALLOWED") for n in notes), notes)

    def test_a_commit_trailer_still_excuses_with_no_pr_body(self):  # control
        r = self.r
        r.sh("commit", "-q", "--amend", "-m", "Bring Card back\n\nDrops-lines: app.txt -- the owner wants Card back")
        got, notes = C.check(r.dir, "origin/main", "HEAD")
        self.assertEqual(got, [])
        self.assertEqual(notes, ["ALLOWED app.txt: the owner wants Card back"])

    # Trailer rule for the body: drop fenced blocks and <!-- --> comments first, then only the last paragraph counts.
    LINE = "Drops-lines: app.txt -- the owner wants Card back"

    def excused(self, body):
        got, notes = C.check(self.r.dir, "origin/main", "HEAD", pr_body=body)
        return got == [] and notes == ["ALLOWED app.txt: the owner wants Card back"], (got, notes)

    def assert_nothing_excused(self, bodies):
        for body in bodies:
            with self.subTest(body=body):
                got, notes = C.check(self.r.dir, "origin/main", "HEAD", pr_body=body)
                self.assertTrue(any("app.txt" in p and "undoing" in p for p in got), got)
                self.assertFalse(any(n.startswith("ALLOWED") for n in notes), notes)

    def test_a_line_inside_a_fenced_block_excuses_nothing(self):
        L = self.LINE
        self.assert_nothing_excused([
            "```\n%s\n```\n" % L,
            "Example of the trailer:\n\n```\n%s\n```\n" % L,
            "```text\n%s\n```\n\nDone.\n" % L,
            "~~~\n%s\n~~~\n" % L,
        ])

    def test_a_line_inside_an_html_comment_excuses_nothing(self):
        L = self.LINE
        self.assert_nothing_excused([
            "<!--\n%s\n-->\n" % L,
            "<!-- template\n%s -->\n" % L,
            "Summary.\n\n<!--\nold note\n\n%s\n-->\n" % L,
            "<!-- %s -->\n" % L,  # not at column 0: a guard that must stay green
        ])

    def test_a_line_in_an_earlier_paragraph_excuses_nothing(self):
        L = self.LINE
        self.assert_nothing_excused([
            "%s\n\nSome closing prose.\n" % L,
            "Summary.\n\n%s\n\nTest plan: ran it.\n" % L,
        ])

    def test_a_line_in_the_last_paragraph_excuses_its_path(self):  # control
        L = self.LINE
        for body in ("Summary.\n\n%s\n" % L,
                     "Summary.\n\nCo-Authored-By: x <x@x>\n%s\n" % L,
                     "%s\n" % L):
            with self.subTest(body=body):
                ok, why = self.excused(body)
                self.assertTrue(ok, why)

    def test_trailing_blank_lines_a_fence_or_a_comment_do_not_hide_the_last_paragraph(self):  # control
        # Pick: drop fences and comments first, then take the last paragraph. A PR template often ends with a
        # checklist fence or a comment; the trailer above it is still the last prose paragraph.
        L = self.LINE
        for body in ("Summary.\n\n%s\n\n\n" % L,
                     "Summary.\n\n%s\n\n```\nlog output\n\nmore\n```\n" % L,
                     "Summary.\n\n%s\n\n<!--\nreviewer note\n-->\n" % L,
                     "Summary.\n\n%s\n\n```\nx\n```\n\n<!-- y -->\n\n" % L):
            with self.subTest(body=body):
                ok, why = self.excused(body)
                self.assertTrue(ok, why)

    # Claude Code ends every PR body with one attribution paragraph. A trailer just above it must still count.
    ATTR = "\U0001F916 Generated with [Claude Code](https://claude.com/claude-code)"

    def test_a_trailer_above_the_attribution_paragraph_excuses_its_path(self):
        L, A = self.LINE, self.ATTR
        for body in ("Summary.\n\n%s\n\n%s\n" % (L, A),
                     "Summary.\n\n%s\n\n  %s  \n\n\n" % (L, A),
                     "Summary.\n\n%s\n\n%s\n" % (L, A.split(" ", 1)[1])):  # without the emoji
            with self.subTest(body=body):
                ok, why = self.excused(body)
                self.assertTrue(ok, why)

    def test_a_trailer_above_the_attribution_paragraph_excuses_its_path_with_crlf(self):
        L, A = self.LINE, self.ATTR
        ok, why = self.excused("Summary.\r\n\r\n%s\r\n\r\n%s\r\n" % (L, A))
        self.assertTrue(ok, why)

    def test_a_trailer_above_the_attribution_and_more_prose_excuses_nothing(self):  # control
        L, A = self.LINE, self.ATTR
        self.assert_nothing_excused(["Summary.\n\n%s\n\n%s\n\nClosing prose.\n" % (L, A)])

    def test_a_trailer_in_the_same_paragraph_as_the_attribution_still_excuses(self):  # control, current behaviour
        L, A = self.LINE, self.ATTR
        ok, why = self.excused("Summary.\n\n%s\n%s\n" % (L, A))
        self.assertTrue(ok, why)

    def test_a_paragraph_with_other_text_and_the_attribution_is_not_skipped(self):  # control
        L, A = self.LINE, self.ATTR
        self.assert_nothing_excused(["Summary.\n\n%s\n\nSee notes. %s\n" % (L, A),
                                     "Summary.\n\n%s\n\n%s extra\n" % (L, A),
                                     "Summary.\n\n%s\n\nNotes:\n%s\n" % (L, A)])

    # The GitHub posting tool appends a footer: a `---` rule, then the Generated-by line. Batch #668 put its trailer above it.
    FOOT = "_Generated by [Claude Code](https://claude.ai/code/session_01MVD32PXm1757wMqHinaZZG)_"

    def test_a_trailer_above_the_posting_footer_excuses_its_path(self):
        L, F, A = self.LINE, self.FOOT, self.ATTR
        for body in ("Summary.\n\n%s\n\n---\n%s" % (L, F),  # the #668 shape
                     "Summary.\n\n%s\n\n---\n\n%s\n" % (L, F),
                     "Summary.\r\n\r\n%s\r\n\r\n---\r\n%s\r\n" % (L, F),
                     "Summary.\n\n%s\n\n%s\n\n---\n%s\n" % (L, A, F),
                     "Summary.\n\n%s\n\n  ---  \n  %s  \n\n\n" % (L, F.replace("https://claude.ai/code/session_01MVD32PXm1757wMqHinaZZG", "https://claude.ai/code"))):
            with self.subTest(body=body):
                ok, why = self.excused(body)
                self.assertTrue(ok, why)

    def test_a_trailer_above_prose_and_the_posting_footer_excuses_nothing(self):  # control
        L, F = self.LINE, self.FOOT
        self.assert_nothing_excused(["Summary.\n\n%s\n\nClosing prose.\n\n---\n%s\n" % (L, F),
                                     "Summary.\n\n%s\n\n---\n\nClosing prose.\n" % L,
                                     "Summary.\n\n%s\n\n---\nSee %s\n" % (L, F),
                                     "Summary.\n\n%s\n\n---\n%s extra\n" % (L, F),
                                     "Summary.\n\n%s\n\nNotes\n---\n%s\n" % (L, F),
                                     "Summary.\n\n%s\n\n%s\n" % (L, F)])  # no rule: not the posting footer


BLOCK = "alpha one\nbeta two\ngamma three\ndelta four\nepsilon five\nzeta six\n"


class Debt19(unittest.TestCase):
    """The three shapes that walked past the banchi revert guard: age, re-wording, a widened hunk."""

    def setUp(self):
        r = self.r = Repo()
        r.put("app.txt", BODY + BLOCK)
        r.put("other.txt", "other v1\n")
        r.commit("base")
        r.push()

    def pr_deletes_block(self):
        r = self.r
        r.sh("checkout", "-q", "-b", "pr1")
        r.commit("delete block", app_txt=BODY)
        r.sh("checkout", "-q", "main")
        r.sh("merge", "-q", "--no-ff", "-m", "Merge pull request #1", "pr1")
        r.push()

    def test_age_is_read_without_a_floor(self):
        r = self.r
        r.sh("checkout", "-q", "-b", "stale")
        r.sh("checkout", "-q", "main")
        self.pr_deletes_block()
        for i in range(6):
            r.commit("filler %d" % i, other_txt="other v%d\n" % (i + 2))
        r.push()
        r.sh("checkout", "-q", "stale")
        r.commit("wording", other_txt="mine\n")
        r.sh("merge", "-q", "-s", "ours", "--no-edit", "main")
        got = r.verdict()
        self.assertTrue(any("app.txt" in p for p in got), got)

    def test_restored_block_with_one_line_reworded(self):
        self.pr_deletes_block()
        r = self.r
        r.sh("checkout", "-q", "-b", "reword")
        r.commit("restore", app_txt=BODY + BLOCK.replace("delta four", "delta 4, reworded"))
        got = r.verdict()
        self.assertTrue(any("app.txt" in p for p in got), got)

    def test_reversal_widened_by_an_adjacent_edit(self):
        self.pr_deletes_block()
        r = self.r
        r.sh("checkout", "-q", "-b", "widen")
        r.commit("restore and touch the line above", app_txt=BODY.replace("line 20\n", "line 20 edited\n") + BLOCK)
        got = r.verdict()
        self.assertTrue(any("app.txt" in p for p in got), got)

    def test_two_lines_reworded_is_a_new_edit(self):
        self.pr_deletes_block()
        r = self.r
        r.sh("checkout", "-q", "-b", "newedit")
        r.commit("rewrite", app_txt=BODY + "alpha 1\nbeta 2\ngamma three\ndelta four\nepsilon five\nzeta six\n")
        self.assertEqual(r.verdict(), [])  # the stated ceiling: more than one altered line is a new edit


class Stale(unittest.TestCase):
    """Single-parent form: main gained lines after the branch was cut, and
    the branch carries a version without them. A rebase moves the cut to the rebase base, and that
    commit is read. The dates do not set the window."""
    T0, T1, T2 = "2026-01-01T10:00:00", "2026-01-02T10:00:00", "2026-01-03T10:00:00"

    def setUp(self):
        r = self.r = Repo()
        r.put("app.txt", BODY)
        r.put("other.txt", "other v1\n")
        r.commit("base", date="2025-12-01T10:00:00")
        r.push()
        r.sh("checkout", "-q", "-b", "feat")
        # the branch edits the line next to where main will insert
        r.commit("feat edits line 5", date=self.T0, app_txt=BODY.replace("line 5\n", "line 5 B\n"))
        r.sh("checkout", "-q", "main")
        r.commit("A adds lines", date=self.T1, app_txt=BODY.replace("line 5\n", "line 5\nA new 1\nA new 2\n"))
        r.push()
        r.sh("checkout", "-q", "feat")

    def land_squash(self):
        r = self.r
        r.sh("checkout", "-q", "main")
        r.sh("merge", "--squash", "feat")
        r.sh("commit", "-q", "-m", "squash feat", date=self.T2)

    def land_merge(self):
        r = self.r
        r.sh("checkout", "-q", "main")
        r.sh("merge", "--no-ff", "-m", "Merge feat", "feat", date=self.T2)

    def hits(self):
        return [h for h in C.history(self.r.dir, "main", 60)[1] if "app.txt" in h]

    def rebase_takes_its_own_side(self):
        self.r.sh("rebase", "-X", "theirs", "main")

    def rewrite_from_a_stale_copy(self):
        r = self.r
        r.sh("merge", "-X", "theirs", "--no-edit", "main", date=self.T1)  # A is now in the branch
        r.commit("rewrite app.txt from the copy read before A", date=self.T2,
                 app_txt=BODY.replace("line 5\n", "line 5 B\n"))

    def test_rebase_takes_ours_is_red_on_the_branch(self):
        self.rebase_takes_its_own_side()
        got = self.r.verdict()
        self.assertTrue(any("app.txt" in p for p in got), got)

    def test_rebase_takes_ours_is_red_landed_as_squash(self):
        self.rebase_takes_its_own_side()
        self.land_squash()
        self.assertTrue(self.hits())

    def test_rebase_takes_ours_is_red_landed_as_merge_commit(self):
        self.rebase_takes_its_own_side()
        self.land_merge()
        self.assertTrue(self.hits())

    def test_stale_rewrite_is_red_on_the_branch(self):
        self.rewrite_from_a_stale_copy()
        got = self.r.verdict()
        self.assertTrue(any("app.txt" in p for p in got), got)

    def test_stale_rewrite_is_red_landed_as_squash(self):
        self.rewrite_from_a_stale_copy()
        self.land_squash()
        self.assertTrue(self.hits())

    def test_stale_rewrite_is_red_landed_as_merge_commit(self):
        self.rewrite_from_a_stale_copy()
        self.land_merge()
        self.assertTrue(self.hits())

    def test_main_work_before_the_cut_is_not_read(self):
        """Cry-wolf guard: lines main gained BEFORE the fork point may be removed on purpose.
        Main gains A's lines, then one more commit (the fork commit); the window starts there, so A is outside it."""
        r = self.r
        r.sh("checkout", "-q", "main")
        r.commit("main moves on past A", date="2026-01-15T10:00:00", other_txt="other v2\n")
        r.push()  # origin/main must move past A, or the fork point resolves to A and the test goes red
        r.sh("checkout", "-q", "-B", "late", "main")
        r.commit("late work removes A's lines on purpose", date="2026-02-01T10:00:00", app_txt=BODY)
        self.assertEqual(r.verdict(), [])

    def test_similar_looking_lines_do_not_hide_a_drop(self):
        """`A new 1` and `B new 1` read alike. A merge that swaps one for the other drops main's line."""
        r = self.r
        first = r.sh("rev-list", "--max-parents=0", "main")
        r.sh("checkout", "-q", "-B", "swap", first)
        r.commit("swap branch work", date=self.T0, other_txt="other v2\n")
        r.sh("merge", "--no-commit", "--no-ff", "main")
        r.put("app.txt", BODY.replace("line 5\n", "line 5\nB new 1\nB new 2\n"))
        r.sh("add", "-A")
        r.sh("commit", "-q", "-m", "Merge main", date=self.T2)
        got = r.verdict()
        self.assertTrue(any("A new 1" in p for p in got), got)

    def test_a_real_rewrite_by_the_resolver_is_not_a_drop(self):
        r = self.r
        first = r.sh("rev-list", "--max-parents=0", "main")
        r.sh("checkout", "-q", "-B", "rw", first)
        r.commit("rw branch work", date=self.T0, other_txt="other v2\n")
        r.sh("merge", "--no-commit", "--no-ff", "main")
        r.put("app.txt", BODY.replace("line 5\n", "line 5\nA new 1 \nA new 2.\n"))
        r.sh("add", "-A")
        r.sh("commit", "-q", "-m", "Merge main", date=self.T2)
        self.assertEqual(r.verdict(), [])


class Value(unittest.TestCase):
    """A stale value overwrite in its smallest form: A changed one value line, and
    the branch carries the old one back. Similar lines must not hide it."""
    T0, T1, T2 = "2026-01-01T10:00:00", "2026-01-02T10:00:00", "2026-01-03T10:00:00"
    PAIRS = [("retries = 4", "retries = 5"), ("ten minutes", "one hour")]

    def build(self, old, new):
        r = self.r = Repo()
        text = lambda first, val: "".join("l%d\n" % i for i in range(1, 6)) + first + "\n" + val + "\n" + "tail\n"
        r.put("cfg.txt", text("head", old))
        r.commit("base", date="2025-12-01T10:00:00", cfg_txt=text("head", old))
        r.push()
        r.sh("checkout", "-q", "-b", "feat")
        r.commit("feat edits the line above", date=self.T0, cfg_txt=text("head B", old))
        r.sh("checkout", "-q", "main")
        r.commit("A changes the value", date=self.T1, cfg_txt=text("head", new))
        r.push()
        r.sh("checkout", "-q", "feat")

    def test_rebase_that_takes_its_own_side_restores_the_old_value(self):
        for old, new in self.PAIRS:
            with self.subTest(old=old):
                self.build(old, new)
                self.r.sh("rebase", "-X", "theirs", "main")
                got = self.r.verdict()
                self.assertTrue(any("cfg.txt" in p for p in got), got)

    def test_merge_taking_ours_restores_the_old_value(self):
        for old, new in self.PAIRS:
            with self.subTest(old=old):
                self.build(old, new)
                self.r.sh("merge", "-X", "ours", "--no-edit", "main", date=self.T2)
                got = self.r.verdict()
                self.assertTrue(any("cfg.txt" in p and "drops" in p for p in got), got)

    def test_a_third_value_is_a_rewrite_not_a_reversal(self):
        """Both sides changed the line, and the resolver picked a value that is neither."""
        r = self.r = Repo()
        text = lambda val: "".join("l%d\n" % i for i in range(1, 6)) + val + "\ntail\n"
        r.commit("base", date="2025-12-01T10:00:00", cfg_txt=text("RULE_FLOOR = 80"))
        r.push()
        r.sh("checkout", "-q", "-b", "feat")
        r.commit("feat bumps", date=self.T0, cfg_txt=text("RULE_FLOOR = 85"))
        r.sh("checkout", "-q", "main")
        r.commit("main bumps", date=self.T1, cfg_txt=text("RULE_FLOOR = 91"))
        r.push()
        r.sh("checkout", "-q", "feat")
        r.sh("merge", "main", ok=False)
        r.put("cfg.txt", text("RULE_FLOOR = 94"))
        r.sh("add", "-A")
        r.sh("commit", "-q", "-m", "Merge main", date=self.T2)
        self.assertEqual(r.verdict(), [])

    def test_a_re_wrapped_paragraph_is_not_a_drop(self):
        r = self.r = Repo()
        body = "".join("l%d\n" % i for i in range(1, 8))
        r.commit("base", date="2025-12-01T10:00:00", doc_txt=body)
        r.push()
        r.sh("checkout", "-q", "-b", "feat")
        r.commit("feat", date=self.T0, other_txt="x\n")
        r.sh("checkout", "-q", "main")
        r.commit("A adds a paragraph", date=self.T1, doc_txt=body.replace("l3\n", "l3\nalpha beta gamma delta\nepsilon zeta eta theta\niota kappa\n"))
        r.push()
        r.sh("checkout", "-q", "feat")
        r.sh("merge", "--no-edit", "main", date=self.T1)
        r.commit("re-wrap it", date=self.T2, doc_txt=body.replace("l3\n", "l3\nalpha beta gamma\ndelta epsilon zeta eta\ntheta iota kappa\n"))
        self.assertEqual(r.verdict(), [])


class Flips(unittest.TestCase):
    """Lines that look alike but state something else must not pass as a rewrite."""
    T0, T1, T2 = "2026-01-01T10:00:00", "2026-01-02T10:00:00", "2026-01-03T10:00:00"

    def resolve(self, base_line, a_line, result_line):
        """main changes base_line to a_line (A). The branch merges main by hand and writes result_line."""
        r = self.r = Repo()
        text = lambda v: "".join("l%d\n" % i for i in range(1, 6)) + (v + "\n" if v else "") + "tail\n"
        r.commit("base", date="2025-12-01T10:00:00", cfg_txt=text(base_line))
        r.push()
        r.sh("checkout", "-q", "-b", "feat")
        r.commit("feat", date=self.T0, other_txt="x\n")
        r.sh("checkout", "-q", "main")
        r.commit("A", date=self.T1, cfg_txt=text(a_line))
        r.push()
        r.sh("checkout", "-q", "feat")
        r.sh("merge", "--no-commit", "--no-ff", "main")
        r.put("cfg.txt", text(result_line))
        r.sh("add", "-A")
        r.sh("commit", "-q", "-m", "Merge main", date=self.T2)
        return r.verdict()

    def red(self, *case):
        got = self.resolve(*case)
        self.assertTrue(any("cfg.txt" in p for p in got), (case, got))

    def test_a_stale_value_with_trailing_tokens_is_the_base_line(self):
        for tail in (" #s", ",", ";"):
            with self.subTest(tail=tail):
                self.red("timeout = 30", "timeout = 60", "timeout = 30" + tail)

    def test_a_negation_flip_is_not_a_rewrite(self):
        self.red("deploy now", "do not deploy now", "do deploy now!")
        self.red("deploy now", "never deploy now", "deploy now")

    def test_an_operator_flip_is_not_a_rewrite(self):
        self.red("x == 5", "x < 5", "x >= 5")
        self.red("a * b", "a - b", "a + b")

    def test_a_line_pasted_into_a_comment_is_not_a_re_wrap(self):
        self.red("", "timeout = 60", "# was timeout = 60 before")

    def test_a_line_that_only_gained_an_argument_passes(self):
        self.assertEqual(self.resolve("run(a, b)", "run(a, b, env=e)", "run(a, b, env=e, timeout=T)"), [])

    def test_a_third_value_still_passes(self):
        self.assertEqual(self.resolve("RULE_FLOOR = 80", "RULE_FLOOR = 91", "RULE_FLOOR = 94"), [])


class OwnHistory(unittest.TestCase):
    """A line the branch alone added is the branch's work. Removing it later, or in a merge, is no loss."""
    T0, T1, T2 = "2026-01-01T10:00:00", "2026-01-02T10:00:00", "2026-01-03T10:00:00"

    def setUp(self):
        r = self.r = Repo()
        r.put("app.txt", BODY)
        r.commit("base", date="2025-12-01T10:00:00", other_txt="o1\n")
        r.push()
        r.sh("checkout", "-q", "-b", "feat")
        r.commit("feat adds a line", date=self.T0, app_txt=BODY + "own line one\nown line two\n")

    def main_moves(self, n, date):
        r = self.r
        r.sh("checkout", "-q", "main")
        r.commit("main moves %d" % n, date=date, other_txt="o%d\n" % n)
        r.push()
        r.sh("checkout", "-q", "feat")

    def merge_dropping_own_lines(self, date):
        r = self.r
        r.sh("merge", "--no-commit", "--no-ff", "main")
        r.put("app.txt", BODY)
        r.sh("add", "-A")
        r.sh("commit", "-q", "-m", "Merge main, drop my own lines", date=date)

    def test_a_merge_that_removes_the_branchs_own_lines_is_green(self):
        self.main_moves(2, self.T1)
        self.merge_dropping_own_lines(self.T2)
        self.assertEqual(self.r.verdict(), [])

    def test_the_same_through_a_second_in_branch_merge_of_main(self):
        r = self.r
        self.main_moves(2, self.T1)
        r.sh("merge", "--no-edit", "main", date=self.T1)  # keeps the lines
        self.main_moves(3, self.T2)
        self.merge_dropping_own_lines(self.T2)
        self.assertEqual(r.verdict(), [])

    def test_a_later_branch_commit_that_removes_them_is_green(self):
        self.main_moves(2, self.T1)
        r = self.r
        r.commit("remove my lines", date=self.T2, app_txt=BODY)
        r.sh("merge", "--no-edit", "main", date=self.T2)
        self.assertEqual(r.verdict(), [])

    def test_a_flagged_line_is_printed_in_full_with_no_cap(self):
        r = self.r
        r.sh("checkout", "-q", "main")
        lines = "".join("main added line number %d with a long tail %s\n" % (i, "x" * 150) for i in range(8))
        r.commit("main adds many", date=self.T1, app_txt=BODY + lines)
        r.push()
        r.sh("checkout", "-q", "feat")
        r.sh("merge", "--no-commit", "--no-ff", "main", ok=False)
        r.sh("checkout", "--ours", "app.txt")
        r.sh("add", "-A")
        r.sh("commit", "-q", "-m", "Merge main taking ours", date=self.T2)
        got = "\n".join(r.verdict())
        for i in range(8):
            self.assertIn("main added line number %d with a long tail %s" % (i, "x" * 150), got)


class IntegrationBase(unittest.TestCase):
    """This repo merges through integration branches. A PR based on `integ` is checked against
    origin/integ, and main's lines are not integ's: a parent that integ lacks can still carry them."""
    T0, T1, T2 = "2026-01-01T10:00:00", "2026-01-02T10:00:00", "2026-01-03T10:00:00"

    def test_merging_main_with_ours_into_a_pr_on_integ_is_red(self):
        r = Repo()
        text = lambda v: "".join("l%d\n" % i for i in range(1, 6)) + v + "\ntail\n"
        r.commit("base", date="2025-12-01T10:00:00", cfg_txt=text("timeout = 30"))
        r.push()
        r.sh("checkout", "-q", "-b", "integ")
        r.commit("integ moves", date=self.T0, other_txt="integ\n")
        r.sh("push", "-q", "origin", "integ")
        r.sh("checkout", "-q", "-b", "feat")
        r.commit("feat edits the line above", date=self.T0, cfg_txt=text("timeout = 30").replace("l5\n", "l5 B\n"))
        r.sh("checkout", "-q", "main")
        r.commit("A", date=self.T1, cfg_txt=text("timeout = 60"))
        r.push()
        r.sh("checkout", "-q", "feat")
        r.sh("merge", "-X", "ours", "--no-edit", "main", date=self.T2)
        r.sh("fetch", "-q", "origin")
        got, _ = C.check(r.dir, "origin/integ", "HEAD")
        self.assertTrue(any("cfg.txt" in p and "timeout = 60" in p for p in got), got)


class Green(unittest.TestCase):
    def setUp(self):
        self.r = base_repo()

    def test_clean_merge_keeping_both_sides(self):
        r = self.r
        r.sh("checkout", "-q", "-b", "feat")
        r.commit("feat", other_txt="other v2\n")
        r.sh("checkout", "-q", "main")
        r.commit("main", app_txt=BODY + "function Card() {}\nmore\n")
        r.push()
        r.sh("checkout", "-q", "feat")
        r.sh("merge", "-q", "--no-edit", "main")
        self.assertEqual(r.verdict(), [])

    def test_unrelated_branch_and_branch_at_main(self):
        r = self.r
        self.assertEqual(r.verdict(), [])
        r.sh("checkout", "-q", "-b", "feat")
        r.commit("feat", other_txt="other v2\n")
        self.assertEqual(r.verdict(), [])

    def test_pure_move_to_another_file(self):
        r = self.r
        r.sh("checkout", "-q", "-b", "feat")
        r.commit("feat", other_txt="other v2\n")
        r.sh("checkout", "-q", "main")
        r.commit("main adds", app_txt=BODY + "function Card() {}\nmoved fn\n")
        r.push()
        r.sh("checkout", "-q", "feat")
        r.sh("merge", "--no-commit", "--no-ff", "main")
        r.put("app.txt", BODY + "function Card() {}\n")
        r.put("other.txt", "other v2\nmoved fn\n")
        r.sh("add", "-A")
        r.sh("commit", "-q", "-m", "Merge main, move fn")
        self.assertEqual(r.verdict(), [])

    def test_reorder_inside_a_file(self):
        r = self.r
        r.sh("checkout", "-q", "-b", "feat")
        r.commit("feat", other_txt="other v2\n")
        r.sh("checkout", "-q", "main")
        r.commit("main adds", app_txt=BODY + "function Card() {}\nfirst\nsecond\n")
        r.push()
        r.sh("checkout", "-q", "feat")
        r.sh("merge", "--no-commit", "--no-ff", "main")
        r.put("app.txt", BODY + "function Card() {}\nsecond\nfirst\n")
        r.sh("add", "-A")
        r.sh("commit", "-q", "-m", "Merge main, reorder")
        self.assertEqual(r.verdict(), [])

    def test_whitespace_only_rewrite_of_a_merged_line(self):
        r = self.r
        r.sh("checkout", "-q", "-b", "feat")
        r.commit("feat", other_txt="other v2\n")
        r.sh("checkout", "-q", "main")
        r.commit("main adds", app_txt=BODY + "function Card() {}\nif (x) { go(); }\n")
        r.push()
        r.sh("checkout", "-q", "feat")
        r.sh("merge", "--no-commit", "--no-ff", "main")
        r.put("app.txt", BODY + "function Card() {}\n    if (x)   { go(); }\n")
        r.sh("add", "-A")
        r.sh("commit", "-q", "-m", "Merge main, reindent")
        self.assertEqual(r.verdict(), [])

    def test_whitespace_only_flip_is_not_a_reversal(self):
        r = self.r
        r.sh("checkout", "-q", "-b", "pr1")
        r.commit("reindent", app_txt=BODY + "function  Card()  {}\n")
        r.sh("checkout", "-q", "main")
        r.sh("merge", "-q", "--no-ff", "-m", "Merge pull request #1", "pr1")
        r.push()
        r.sh("checkout", "-q", "-b", "back")
        r.commit("reindent back", app_txt=BODY + "function Card() {}\n")
        self.assertEqual(r.verdict(), [])


WORKFLOW_YML = """\
name: {name}
on:
  pull_request:
  push:
    branches: [main]
{perm}jobs:
  gate:
    runs-on: ubuntu-latest
{t_build}    steps:
{pins}      - name: Check out
        uses: actions/checkout@v4
      - name: Run the gate
        run: python3 lint/run_gate.py
      - name: Run the unit tests
        run: python3 -m unittest discover -s lint
      - name: Report the result
        run: python3 lint/report.py --format json
{allpass}  lint:
    runs-on: ubuntu-latest
{t_lint}    steps:
      - name: Check out
        uses: actions/checkout@v4
      - name: Lint the shell and the YAML
        run: python3 lint/run_lint.py --strict
"""
PERM = "permissions: read-all\n"
TIMEOUT = "    timeout-minutes: 15\n"
PIN = "      - uses: actions/setup-python@0b93645e9fea7318ecaed2b359559ac225c90a2b # v5.3.0\n"
PIN_BUMPED = "      - uses: actions/setup-python@f3e1a7c9d2b45a60e8d1c4b7a9f20e3d5c6b8a71 # v5.4.0\n"
PINS = PIN + "".join("      - uses: actions/%s@%s # %s\n" % x for x in (
    ("cache", "6849a6489940f00c2f30c0fb92c6274307ccb58a", "v4.1.2"),
    ("upload-artifact", "b4b15b8c7c6ac21ea08fcf65892d2ee8f75cf882", "v4.4.3")))


def workflow(name="gates", perm="", t_build="", t_lint="", pins="", allpass=""):
    """The workflow file as the base has it. Each block keyword is what main's earlier PR adds."""
    return WORKFLOW_YML.format(name=name, perm=perm, t_build=t_build, t_lint=t_lint, pins=pins, allpass=allpass)


def after_51(**edits):
    """The workflow once PR 51 has landed: a unique line, three pin lines, and one line added in two jobs."""
    return workflow(**dict(dict(perm=PERM, t_build=TIMEOUT, t_lint=TIMEOUT, pins=PINS), **edits))


class RenamedFile(unittest.TestCase):
    """Under --no-renames a rename reads as a delete plus an add, so the file it left looks reverted.
    A renamed file must get the verdict the same edits get in place: green for what the rename carries,
    refused for what it drops. Incident: joyous 53 renamed gates.yml to checks.yml, then bumped pins that
    PR 51 had added to gates.yml. The check refused with `hunk reversed`, and nothing was lost.
    PR 51 adds, in separate hunks: PERM (one line), PINS (three lines), and TIMEOUT in two jobs."""
    OLD, NEW = ".github/workflows/gates.yml", ".github/workflows/checks.yml"

    def setUp(self):
        r = self.r = Repo()
        r.put(self.OLD, workflow())
        r.commit("base")
        r.push()

    def land_51(self):
        r = self.r
        r.sh("checkout", "-q", "-b", "pr51")
        r.put(self.OLD, after_51())
        r.commit("add the pins and the limits")
        r.sh("checkout", "-q", "main")
        r.sh("merge", "-q", "--no-ff", "-m", "Merge pull request #51", "pr51")
        r.push()

    def rename(self, text):
        r = self.r
        r.sh("mv", self.OLD, self.NEW)
        r.put(self.NEW, text)
        r.commit("rename gates to checks")

    def paired(self):
        """Status letters git gives the branch against main with renames on: R when it pairs the file, A and D when not."""
        return sorted(line[0] for line in self.r.sh("diff", "-M", "--name-status", "origin/main", "HEAD").splitlines())

    def assertRefused(self, got):
        self.assertTrue(any(("gates.yml" in p or "checks.yml" in p) and "undoing" in p for p in got), got)

    def test_a_pure_rename_of_a_file_main_added_lines_to_is_green(self):
        self.land_51()
        self.r.sh("checkout", "-q", "-b", "ren")
        self.rename(after_51())
        self.assertEqual(self.paired(), ["R"])
        self.assertEqual(self.r.verdict(), [])

    def test_a_rename_with_a_name_edit_and_a_pin_bump_is_green(self):
        """The incident. Control: the same two edits in place are green (next test), so the rename alone decides."""
        self.land_51()
        self.r.sh("checkout", "-q", "-b", "ren")
        self.rename(after_51(name="checks", pins=PINS.replace(PIN, PIN_BUMPED)))
        self.assertEqual(self.paired(), ["R"])
        self.assertEqual(self.r.verdict(), [])

    def test_the_same_name_edit_and_pin_bump_in_place_is_green(self):  # control
        self.land_51()
        self.r.sh("checkout", "-q", "-b", "bump")
        self.r.put(self.OLD, after_51(name="checks", pins=PINS.replace(PIN, PIN_BUMPED)))
        self.r.commit("edit the name and bump a pin")
        self.assertEqual(self.r.verdict(), [])

    def test_a_rename_that_deletes_a_line_main_added_is_refused(self):
        self.land_51()
        self.r.sh("checkout", "-q", "-b", "ren")
        self.rename(after_51(perm=""))
        self.assertEqual(self.paired(), ["R"])
        self.assertRefused(self.r.verdict())

    def test_a_rename_that_drops_one_of_two_identical_added_lines_is_refused(self):
        """Main added the line twice. One copy stays in the new path, and that copy is no move for the one that went."""
        self.land_51()
        self.r.sh("checkout", "-q", "-b", "ren")
        self.rename(after_51(t_lint=""))
        self.assertEqual(self.paired(), ["R"])
        self.assertRefused(self.r.verdict())

    def test_a_rename_git_does_not_pair_that_drops_a_line_main_added_is_refused(self):
        """Under 50 percent alike git reports a delete and an add. The check fails closed: the drop still shows."""
        self.land_51()
        self.r.sh("checkout", "-q", "-b", "ren")
        notes = "".join("  # step %d: a note the old file does not hold, with a long tail of its own %s\n" % (i, "x" * 60) for i in range(30))
        self.rename(after_51(name="checks", perm="").replace("jobs:\n", notes + "jobs:\n"))
        self.assertEqual(self.paired(), ["A", "D"])
        self.assertRefused(self.r.verdict())

    def cut_rename_then_merge_main(self):
        """A branch cut before PR 51 renames the file, then merges main: git carries PR 51's lines to the new path."""
        r = self.r
        r.sh("checkout", "-q", "-b", "ren")
        self.rename(workflow(name="checks"))
        r.sh("checkout", "-q", "main")
        self.land_51()
        r.sh("checkout", "-q", "ren")
        r.sh("merge", "-q", "--no-edit", "origin/main")
        self.assertEqual(r.sh("show", "HEAD:" + self.NEW), after_51(name="checks").strip(), "the merge must carry PR 51 across the rename")

    def test_a_rename_then_a_merge_of_main_is_green(self):
        """The lost-line read: the merge holds every line PR 51 added, under the new name."""
        self.cut_rename_then_merge_main()
        self.assertEqual(self.paired(), ["R"])
        self.assertEqual(self.r.verdict(), [])

    def test_a_rename_then_a_merge_of_main_then_a_pin_bump_is_green(self):
        self.cut_rename_then_merge_main()
        self.r.put(self.NEW, after_51(name="checks", pins=PINS.replace(PIN, PIN_BUMPED)))
        self.r.commit("bump a pin")
        self.assertEqual(self.r.verdict(), [])

    def conflicted_limit(self, renamed, main_renames=False):
        """Main moves the limit 10 to 15, renaming the file first when main_renames; the branch moves it to 20, renamed
        or not; the merge resolves to 30, a third value, at the name the merge keeps."""
        r, limit = self.r, lambda n: workflow(t_build="    timeout-minutes: %d\n" % n)
        r.put(self.OLD, limit(10))
        r.commit("set a limit")
        r.push()
        r.sh("checkout", "-q", "-b", "ren")
        if renamed:
            r.sh("mv", self.OLD, self.NEW)
        r.put(self.NEW if renamed else self.OLD, limit(20))
        r.commit("move the limit to 20")
        r.sh("checkout", "-q", "main")
        if main_renames:
            r.sh("mv", self.OLD, self.NEW)
        r.put(self.NEW if main_renames else self.OLD, limit(15))
        r.commit("move the limit to 15")
        r.push()
        r.sh("checkout", "-q", "ren")
        r.sh("merge", "--no-edit", "origin/main", ok=False)  # both sides moved the line: a conflict
        r.put(self.NEW if renamed or main_renames else self.OLD, limit(30))
        r.sh("add", "-A")
        r.sh("commit", "-q", "--no-edit")

    def test_a_rename_then_a_merge_that_resolves_a_changed_line_to_a_third_value_is_green(self):
        """The lost-line read for a line main changed, not added. In place a third value is a rewrite (the next test)."""
        self.conflicted_limit(renamed=True)
        self.assertEqual(self.paired(), ["R"])
        self.assertEqual(self.r.verdict(), [])

    def test_the_same_merge_with_a_third_value_in_place_is_green(self):  # control
        self.conflicted_limit(renamed=False)
        self.assertEqual(self.r.verdict(), [])

    def test_main_renames_then_a_merge_that_resolves_a_changed_line_to_a_third_value_is_green(self):
        """The mod read for a path main renamed. The base holds the limit only under the old name, so main's edit reads
        across the two names, and the rewrite excuse holds as it does in place (the control above). Read at the new
        name, the base has no such file, the excuse fails, and the merge is refused."""
        self.conflicted_limit(renamed=False, main_renames=True)
        self.assertEqual(self.r.sh("ls-tree", "--name-only", "origin/main", "--", self.OLD), "", "main must rename the file")
        self.assertIn("timeout-minutes: 30", self.r.sh("show", "HEAD:" + self.NEW))
        self.assertEqual(self.r.verdict(), [])


ALLPASS = "      - uses: shivinate7/claude-settings/actions/all-jobs-passed@1cc47f015bdaf073d8cb0f043a988c28d09aa3e1 # main, Oct %d\n"


class PinComment:
    """Steps the pin-comment cases share: the old and new path, the merge of main, and the drop check."""
    OLD, NEW = RenamedFile.OLD, RenamedFile.NEW

    def merge_main(self, resolve=None):
        """Merge main. With resolve, the merge is held, resolve(text) sets the new path, and that is the merge commit."""
        r = self.r
        if resolve is None:
            r.sh("merge", "-q", "--no-edit", "origin/main")
            return
        r.sh("merge", "-q", "--no-commit", "--no-ff", "origin/main")
        with open(os.path.join(r.dir, self.NEW)) as f:
            merged = f.read()
        r.put(self.NEW, resolve(merged))
        r.sh("add", "-A")
        r.sh("commit", "-q", "-m", "Merge main into the rename")

    def assertDropsPinLine(self, got):
        self.assertTrue(any("drops 1 line" in p and "all-jobs-passed" in p for p in got), got)


class RenamedPinComment(PinComment, unittest.TestCase):
    """Main edits one pinned line after the branch cut: only its trailing comment date. The branch renames the file
    and bumps a pin. The merge of main must carry the date to the new path. Git pairs the rename at 90 percent
    similarity in both directions, which can make a merge write the older date (29) where main wrote 30. Cases: a
    merge that carries main's date is green; a merge that drops the line is refused; a merge that writes the older
    date is refused by the line rule. A comment-only change stays a drop, as on main."""

    def setUp(self):
        r = self.r = Repo()
        r.put(self.OLD, workflow(allpass=ALLPASS % 29))
        r.commit("base")
        r.push()
        r.sh("checkout", "-q", "-b", "ren")
        r.sh("mv", self.OLD, self.NEW)
        r.put(self.NEW, workflow(name="checks", pins=PINS.replace(PIN, PIN_BUMPED), allpass=ALLPASS % 29))
        r.commit("rename gates to checks and bump a pin")
        r.sh("checkout", "-q", "main")
        r.put(self.OLD, workflow(allpass=ALLPASS % 30))
        r.commit("main edits the all-jobs-passed date")
        r.push()
        r.sh("checkout", "-q", "ren")

    def test_a_rename_then_a_merge_that_carries_main_s_edited_date_is_green(self):
        self.merge_main()
        self.assertIn((ALLPASS % 30).rstrip("\n"), self.r.sh("show", "HEAD:" + self.NEW))
        self.assertEqual(RenamedFile.paired(self), ["R"])
        self.assertEqual(self.r.verdict(), [])

    def test_a_rename_then_a_merge_that_drops_main_s_edited_line_is_refused(self):
        self.merge_main(resolve=lambda text: text.replace(ALLPASS % 30, ""))
        self.assertNotIn("all-jobs-passed", self.r.sh("show", "HEAD:" + self.NEW))
        self.assertDropsPinLine(self.r.verdict())

    def test_a_rename_then_a_merge_that_writes_the_older_date_is_refused(self):
        """The incident's shape: the same SHA, the older comment date. Refused today by the line rule."""
        self.merge_main(resolve=lambda text: text.replace(ALLPASS % 30, ALLPASS % 29))
        self.assertDropsPinLine(self.r.verdict())


class RenamedOnMain(PinComment, unittest.TestCase):
    """Main renames the file, and the branch edits the pinned line's date on the old name after the cut. The merge
    of main carries that edit to the new path, so it is the branch's own work: green. The check reads main's side of
    the rename, and the base holds the line only under the old name, so the base lookup misses it and the line counts
    as main's and is refused. Twin: main edits the line on the new name and the merge drops that edit: refused."""

    def build(self, main_edits):
        r = self.r = Repo()
        r.put(self.OLD, workflow(allpass=ALLPASS % 29))
        r.commit("base")
        r.push()
        r.sh("checkout", "-q", "-b", "edit")
        branch = workflow(allpass=ALLPASS % 29, pins=PINS.replace(PIN, PIN_BUMPED)) if main_edits else workflow(allpass=ALLPASS % 30)
        r.put(self.OLD, branch)
        r.commit("the branch's own edit on the old name")
        r.sh("checkout", "-q", "main")
        r.sh("mv", self.OLD, self.NEW)
        if main_edits:
            r.put(self.NEW, workflow(allpass=ALLPASS % 30))
        r.commit("rename gates to checks")
        r.push()
        r.sh("checkout", "-q", "edit")

    def test_the_branch_edits_the_old_name_and_a_merge_of_main_that_renamed_it_is_green(self):
        self.build(main_edits=False)
        self.merge_main()
        self.assertIn((ALLPASS % 30).rstrip("\n"), self.r.sh("show", "HEAD:" + self.NEW))
        self.assertEqual(self.r.verdict(), [])

    def test_main_edits_the_line_on_the_new_name_and_a_merge_that_drops_that_edit_is_refused(self):
        self.build(main_edits=True)
        self.merge_main(resolve=lambda text: text.replace(ALLPASS % 30, ""))
        self.assertDropsPinLine(self.r.verdict())


class Unknown(unittest.TestCase):
    def test_no_upstream_is_unknown(self):
        r = Repo()
        r.commit("only", a_txt="x\n")
        with self.assertRaises(C.Unknown):
            C.check(r.dir, "origin/nope", "HEAD")

    def test_shallow_is_unknown(self):
        r = base_repo()
        r.commit("two", other_txt="v2\n")
        r.push()
        sh = os.path.join(r.tmp.name, "shallow")
        subprocess.run(["git", "clone", "-q", "--depth", "1", "file://" + os.path.join(r.tmp.name, "o.git"), sh], check=True, capture_output=True)
        with self.assertRaises(C.Unknown):
            C.check(sh, "origin/main", "HEAD")

    def run_main(self, env_ci, *extra):
        r = Repo()
        r.commit("only", a_txt="x\n")
        old = os.environ.pop("CI", None)
        if env_ci:
            os.environ["CI"] = "1"
        try:
            with contextlib.redirect_stdout(io.StringIO()) as out:
                code = C.main(["--repo", r.dir, "--upstream", "origin/nope", *extra])
        finally:
            os.environ.pop("CI", None)
            if old is not None:
                os.environ["CI"] = old
        return code, out.getvalue()

    def test_unknown_exit_codes(self):
        self.assertEqual(self.run_main(False)[0], 0)
        self.assertEqual(self.run_main(True)[0], 1)
        code, out = self.run_main(False, "--strict")
        self.assertEqual(code, 1)
        self.assertIn("UNKNOWN", out)


class History(unittest.TestCase):
    def test_history_finds_a_landed_stale_merge(self):
        r = base_repo()
        r.sh("checkout", "-q", "-b", "stale")
        r.sh("checkout", "-q", "main")
        r.sh("checkout", "-q", "-b", "pr1")
        r.commit("delete Card", app_txt=BODY)
        r.sh("checkout", "-q", "main")
        r.sh("merge", "-q", "--no-ff", "-m", "Merge pull request #1", "pr1")
        r.sh("checkout", "-q", "stale")
        r.commit("wording", other_txt="v2\n")
        r.sh("merge", "-q", "-s", "ours", "--no-edit", "main")
        r.sh("checkout", "-q", "main")
        r.sh("merge", "-q", "--no-ff", "-m", "Merge pull request #2", "stale")
        n, hits = C.history(r.dir, "main", 60)
        self.assertTrue(any("app.txt" in h and "whole file" in h for h in hits), hits)


class MergeTool(unittest.TestCase):
    def test_merge_tool_refuses_a_stale_branch(self):
        import merge
        r = base_repo()
        r.sh("checkout", "-q", "-b", "stale")
        r.sh("checkout", "-q", "main")
        r.sh("checkout", "-q", "-b", "pr1")
        r.commit("delete Card", app_txt=BODY)
        r.sh("checkout", "-q", "main")
        r.sh("merge", "-q", "--no-ff", "-m", "Merge pull request #1", "pr1")
        r.push()
        r.sh("checkout", "-q", "stale")
        r.commit("wording", other_txt="v2\n")
        r.sh("merge", "-q", "-s", "ours", "--no-edit", "main")
        with self.assertRaises(merge.Stop) as cm:
            merge.undo_check(r.dir, "origin/main")
        self.assertIn("app.txt", str(cm.exception))
        r.sh("checkout", "-q", "main")
        merge.undo_check(r.dir, "origin/main")  # a branch at main: green, no raise


# ------------------------------------------------------ scan cost and NUL lines


def scanner_lines(tag):
    """20 lines of source-like text: comment openers inside strings, a lone apostrophe, a template
    literal over three lines, a pipe, an unbalanced paren. A combined pattern must escape all of them."""
    out = []
    for i in range(4):
        out += ['%s%da = "/* opener %d"' % (tag, i, i), '%s%db = "// slash %d" # hash %d' % (tag, i, i, i),
                "<p>Don't %s%d</p>" % (tag, i), "%s%dc = a | (b %d" % (tag, i, i)]
    return out + ["%s = `template open" % tag, "%s middle" % tag, "%s close`" % tag, "%s plain 20" % tag]


def drop_merge(lines, own=False):
    """A merge commit that drops `lines` from app.txt. own=False: main added them, so upstream holds
    them. own=True: the branch added them itself and main did not. -> (repo, merge sha)."""
    body = BODY + "function Card() {}\n" + "".join(l + "\n" for l in lines)
    r = base_repo()
    r.sh("checkout", "-q", "-b", "feat")
    if own:
        r.commit("feat adds lines", app_txt=body)
        r.sh("checkout", "-q", "main")
        r.commit("main moves", other_txt="other v2\n")
    else:
        r.commit("feat", other_txt="other v2\n")
        r.sh("checkout", "-q", "main")
        r.commit("main adds lines", app_txt=body)
    r.push()
    r.sh("checkout", "-q", "feat")
    r.sh("merge", "--no-commit", "--no-ff", "main")
    r.put("app.txt", BODY + "function Card() {}\n")
    r.sh("add", "-A")
    r.sh("commit", "-q", "-m", "Merge main, drop the lines")
    return r, r.sh("rev-parse", "HEAD")


def git_calls(fn):
    """Run fn with the git helper wrapped. -> (fn's result, [argv tuple of each git call])."""
    calls, real = [], C.git

    def counting(cwd, *a, ok=(0,)):
        calls.append(a)
        return real(cwd, *a, ok=ok)
    with unittest.mock.patch.object(C, "git", counting):
        return fn(), calls


def probes(calls):
    """The calls that find a line's adding commit: a pickaxe, or an ancestry test."""
    return [a for a in calls if (a[0] == "log" and any(x.startswith("-G") for x in a)) or (a[0] == "merge-base" and "--is-ancestor" in a)]


class CallBound(unittest.TestCase):
    """branch_only ran one `git log -G` per lost line, up to OWN_LOOKUPS per file. A merge that drops
    20 lines of one file must cost a fixed number of git calls, not one per line."""

    def lost(self, lines, own=False):
        r, m = drop_merge(lines, own)
        found, calls = git_calls(lambda: C.lost_lines(r.dir, m, ("origin/main",)))
        return r, found, calls

    def test_main_carried_lines_cost_the_same_at_20_as_at_5(self):
        _, found20, c20 = self.lost(scanner_lines("m"))
        _, found5, c5 = self.lost(scanner_lines("m")[:5])
        self.assertEqual([len(x[2]) for x in found20], [20])
        self.assertEqual([len(x[2]) for x in found5], [5])
        self.assertLessEqual(len(c20) - len(c5), 3, "git calls: N=5 %d, N=20 %d, probes at N=20 %d" % (len(c5), len(c20), len(probes(c20))))
        # An absolute bound too: a constant overhead of four probes passes the difference above.
        self.assertLessEqual(len(probes(c20)), 3, "probes at N=20: %d of %d git calls" % (len(probes(c20)), len(c20)))

    def test_own_lines_cost_the_same_at_20_as_at_5(self):
        _, found20, c20 = self.lost(scanner_lines("o"), own=True)
        _, found5, c5 = self.lost(scanner_lines("o")[:5], own=True)
        self.assertEqual(found20, [])
        self.assertEqual(found5, [])
        self.assertLessEqual(len(c20) - len(c5), 3, "git calls: N=5 %d, N=20 %d, probes at N=20 %d" % (len(c5), len(c20), len(probes(c20))))
        self.assertLessEqual(len(probes(c20)), 3, "probes at N=20: %d of %d git calls" % (len(probes(c20)), len(c20)))


class Scanner(unittest.TestCase):
    """Source-like lines are matched as plain text. Main-carried ones are all flagged; the branch's own are none."""

    def test_all_twenty_main_carried_lines_are_flagged(self):
        r, _ = drop_merge(scanner_lines("m"))
        text = "\n".join(r.verdict())
        for line in scanner_lines("m"):
            self.assertIn(" ".join(line.split()), text)

    def test_none_of_the_twenty_own_lines_is_flagged(self):
        r, _ = drop_merge(scanner_lines("o"), own=True)
        self.assertEqual(r.verdict(), [])


class NulLine(unittest.TestCase):
    """A UTF-16 file puts a NUL byte in every line. The line main added and the merge dropped is a FAIL, not a crash.
    A failed read counts the line: branch_only_lines returns set() on Unknown, so the line is never clear."""

    def test_a_utf16_line_main_added_and_the_merge_dropped_is_a_fail(self):
        r = base_repo()
        r.sh("checkout", "-q", "-b", "feat")
        r.commit("feat", other_txt="other v2\n")
        r.sh("checkout", "-q", "main")
        with open(os.path.join(r.dir, "wide.txt"), "wb") as f:
            f.write("main note\n".encode("utf-16"))
        r.sh("add", "-A")
        r.sh("commit", "-q", "-m", "main adds a UTF-16 note")
        r.push()
        r.sh("checkout", "-q", "feat")
        r.sh("merge", "--no-commit", "--no-ff", "main")
        r.sh("rm", "-q", "-f", "wide.txt")
        r.sh("commit", "-q", "-m", "Merge main, drop the note")
        got = r.verdict()
        self.assertTrue(any("wide.txt" in p for p in got), got)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = C.main(["--repo", r.dir, "--upstream", "origin/main"])
        self.assertEqual(code, 1, out.getvalue())
        self.assertIn("FAIL", out.getvalue())
        # A failed read counts the line, so it is never clear.
        self.assertFalse(C.branch_only(r.dir, "HEAD", ["nosuchrev"], "wide.txt", "x", ["HEAD"]))


class OwnContentLines(unittest.TestCase):
    """A line whose content starts `++` or `--` shows in a diff as `+++` or `---`. branch_only_lines drops
    those by prefix, so the branch's own line never finds its adding commit and counts as lost (false FAIL).
    The old per-line `git log -G` read them as content."""

    def test_branch_own_plus_plus_and_dash_dash_lines_dropped_by_the_merge_are_green(self):
        r = base_repo()
        r.sh("checkout", "-q", "-b", "feat")
        r.commit("feat adds a ++ line and a -- note", app_txt=BODY + "function Card() {}\n++i;\n-- note\n")
        r.commit("feat rewords the note", app_txt=BODY + "function Card() {}\n++i;\n-- note v2\n")
        r.sh("checkout", "-q", "main")
        r.commit("main moves", other_txt="other v2\n")
        r.push()
        r.sh("checkout", "-q", "feat")
        r.sh("merge", "--no-commit", "--no-ff", "main")
        r.put("app.txt", BODY + "function Card() {}\n")
        r.sh("add", "-A")
        r.sh("commit", "-q", "-m", "Merge main, drop my lines")
        self.assertEqual(r.verdict(), [])


class BlobReads(unittest.TestCase):
    """Blobs reads `rev:path` through one cat-file process. The header must read the path as one field
    (a path may hold a space), a missing path reads as "" (lost_in_parent reads a deleted file this way),
    and an EOF header means the history cannot be read: Unknown, never an empty blob."""

    def test_a_path_with_a_space_reads_its_text_and_a_missing_one_reads_empty(self):
        r = base_repo()
        r.put("lint/with space.txt", "spaced text\n")
        r.sh("add", "-A")
        r.sh("commit", "-q", "-m", "spaced path")
        b = C.Blobs(r.dir)
        try:
            self.assertEqual(b.get("HEAD", "lint/with space.txt").split(), ["spaced", "text"])
            # A missing path reads as empty: the "missing" reply, a different branch.
            self.assertEqual(b.get("HEAD", "lint/no such.py"), "")
        finally:
            b.close()

    def test_an_eof_header_is_unknown_not_an_empty_blob(self):
        class Dead:
            def __init__(self, *a, **k):
                self.stdin, self.stdout = io.BytesIO(), io.BytesIO(b"")

            def wait(self, *a, **k):
                return 0
        r = base_repo()
        with unittest.mock.patch.object(C.subprocess, "Popen", Dead):
            b = C.Blobs(r.dir)
        with self.assertRaises(C.Unknown):
            b.get("HEAD", "app.txt")


class RawBytes(unittest.TestCase):
    """Control bytes and carriage returns are data. A changed line that holds \\x01 is still one line:
    the log parse splits on \\x01, so the line and its adding commit must survive it. A path that ends in
    \\r must not be read as the path without the \\r: the cat-file line protocol drops that CR."""

    def test_a_branch_line_with_a_control_byte_keeps_its_text_and_its_adder(self):
        r = base_repo()
        r.sh("checkout", "-q", "-b", "feat")
        adder = r.commit("feat adds a control byte", app_txt=BODY + "function Card() {}\nctl\x01char\n")
        base = r.sh("merge-base", "origin/main", "feat")
        got, calls = git_calls(lambda: C.branch_only_lines(r.dir, adder, [base], "app.txt", ["ctl\x01char"], ["origin/main"]))
        self.assertEqual(got, {"ctl\x01char"})
        self.assertEqual([a[2] for a in calls if a[0] == "merge-base" and "--is-ancestor" in a], [adder])

    def test_a_path_ending_in_cr_is_never_read_as_another_path(self):
        r = base_repo()
        b = C.Blobs(r.dir)
        try:
            try:
                got = b.get("HEAD", "app.txt\r")
            except C.Unknown:
                return  # a refusal is a verdict
            self.assertEqual(got, "", "app.txt\\r read as another path: %r" % got[:40])
        finally:
            b.close()


class FailReads:
    """Every read of `rev:path` fails while the block is armed, as a read fails mid-scan: `git show`
    exits 128, and cat-file answers `missing` for a blob it holds. Other reads are real. main reads with
    `git show`; the Blobs reader reads with cat-file, so both are patched. `hits` counts the failed reads."""

    def __init__(self, rev, path):
        self.want, self.hits = "%s:%s" % (rev, path), 0
        self.real_run, self.real_popen = subprocess.run, subprocess.Popen

    def run(self, args, *a, **k):
        if list(args[-2:]) == ["show", self.want]:
            self.hits += 1
            return subprocess.CompletedProcess(args, 128, "", "fatal: injected read failure")
        return self.real_run(args, *a, **k)

    def popen(self, args, *a, **k):
        proc = self.real_popen(args, *a, **k)
        return CatFile(self, proc) if list(args[-2:]) == ["cat-file", "--batch"] else proc

    def armed(self):
        return unittest.mock.patch.multiple(subprocess, run=self.run, Popen=self.popen)


class CatFile:
    """A cat-file process. The reply to a faulted request reads `missing`; its blob is consumed so
    the protocol stays in step for the next request."""

    def __init__(self, fault, proc):
        self.fault, self.proc, self.req = fault, proc, None
        self.stdin, self.stdout = Feed(self), Reply(self)

    def wait(self, *a, **k):
        return self.proc.wait(*a, **k)


class Feed:
    def __init__(self, owner):
        self.owner = owner

    def write(self, data):
        self.owner.req = data.decode("utf-8", "surrogateescape").strip()
        return self.owner.proc.stdin.write(data)

    def flush(self):
        return self.owner.proc.stdin.flush()

    def close(self):
        return self.owner.proc.stdin.close()


class Reply:
    def __init__(self, owner):
        self.owner = owner

    def readline(self):
        o = self.owner
        if o.req == o.fault.want:
            o.fault.hits += 1
            head = o.proc.stdout.readline()
            o.proc.stdout.read(int(head.split()[2]) + 1)
            return (o.req + " missing\n").encode("utf-8", "surrogateescape")
        return o.proc.stdout.readline()

    def read(self, n):
        return self.owner.proc.stdout.read(n)

    def close(self):
        return self.owner.proc.stdout.close()


class SharedLineRead(unittest.TestCase):
    """A file is byte-identical at the merge and at the parent that added its two lines, and the claim
    commit on top does not touch it. The two lines are main's, and the merge keeps them: no drop. A read
    that fails is no text. It may end the check as UNKNOWN, but it must never become a drop, and two
    windows of one merge must agree."""

    DEC = "docs/decisions/fixture-shared-line.md"
    HEAD_TXT = "---\nid: D-618\n---\n\n```refs\ncode: src/a.ts\n```\n\n"
    TAIL_TXT = "**Decision.** Search is Design 1.\n\n- A query is OR.\n- Two lists.\n"
    T0, T1, T2, T3 = "2025-12-01T10:00:00", "2026-01-01T10:00:00", "2026-01-02T10:00:00", "2026-01-03T10:00:00"

    def build(self, lane_edits):
        """The q_max shape. Main adds two lines to the file after the cut. The lane never touches the
        file, or with lane_edits adds a line at its tail. The lane merges main and keeps the lines.
        A claim commit that does not touch the file goes on top. -> (repo, merge sha, claim sha)."""
        r = Repo()
        r.put("app.txt", BODY)
        r.put(self.DEC, self.HEAD_TXT + self.TAIL_TXT)
        r.sh("add", "-A")
        r.sh("commit", "-q", "-m", "base", date=self.T0)
        r.push()
        r.sh("checkout", "-q", "-b", "lane")
        r.put("lane.txt", "lane work\n")
        if lane_edits:
            r.put(self.DEC, self.HEAD_TXT + self.TAIL_TXT + "- Lane note.\n")
        r.sh("add", "-A")
        r.sh("commit", "-q", "-m", "lane work", date=self.T1)
        r.sh("checkout", "-q", "main")
        r.put(self.DEC, self.HEAD_TXT + "Kind: build\nPlan: specs/x.md (web)\n\n" + self.TAIL_TXT)
        r.sh("add", "-A")
        r.sh("commit", "-q", "-m", "main adds kind and plan", date=self.T2)
        r.push()
        r.sh("checkout", "-q", "lane")
        r.sh("merge", "-q", "--no-edit", "origin/main", date=self.T3)
        merged = r.sh("rev-parse", "HEAD")
        r.put("claims.txt", "D-779 D-780\n")
        r.sh("add", "-A")
        r.sh("commit", "-q", "-m", "Claim record numbers", date=self.T3)
        return r, merged, r.sh("rev-parse", "HEAD")

    def outcome(self, r, head):
        try:
            return C.check(r.dir, "origin/main", head)
        except C.Unknown as e:
            return e

    def assertNoDrop(self, got, merged):
        if isinstance(got, C.Unknown):
            return  # a read that cannot run is UNKNOWN, never a drop
        drops = [x for x in got[0] if "drops" in x and merged[:9] in x]
        self.assertEqual(drops, [], "a failed read became a drop")

    def assertSameOrUnknown(self, a, b):
        if isinstance(a, C.Unknown) or isinstance(b, C.Unknown):
            return
        self.assertEqual(a[0], b[0], "the preview window and the confirm window disagree")

    def test_the_q_max_shape_with_a_claim_on_top_is_green(self):
        r, merged, claim = self.build(lane_edits=False)
        self.assertEqual(self.outcome(r, merged)[0], [])
        self.assertEqual(self.outcome(r, claim)[0], [])

    def test_a_lane_that_edits_the_file_and_a_failed_read_is_never_a_drop(self):
        # A failed read of the merge file is never a drop.
        r, merged, claim = self.build(lane_edits=True)
        clean = self.outcome(r, merged)
        self.assertNotIsInstance(clean, C.Unknown)
        self.assertEqual(clean[0], [], "clean without faults")
        fault = FailReads(merged, self.DEC)
        with fault.armed():
            preview = self.outcome(r, merged)
        self.assertGreater(fault.hits, 0, "the faulted read never ran")
        self.assertNoDrop(preview, merged)
        self.assertSameOrUnknown(preview, self.outcome(r, claim))


class Plumb:
    """Trees and commits made with plumbing, never the worktree. Windows refuses a colon in a path
    unless core.protectNTFS is off, so the fixture turns it off: the names become real tree entries."""

    def __init__(self, r):
        self.r, self.n = r, 0

    def run(self, *a, inp=None, env=None):
        p = subprocess.run(["git", "-C", self.r.dir, "-c", "core.protectNTFS=false", *a], input=inp,
                           capture_output=True, env=dict(os.environ, **(env or {})))
        assert p.returncode == 0, (a, p.stderr)
        return p.stdout.decode("utf-8", "replace").strip()

    def blob(self, text):
        return self.run("hash-object", "-w", "--stdin", inp="".join(l + "\n" for l in text).encode("utf-8"))

    def tree(self, entries):
        """entries: (mode, sha, name bytes). -> tree sha, read through a private index file."""
        self.n += 1
        idx = os.path.join(self.r.tmp.name, "index-%d" % self.n)
        rows = b"".join(b"%s %s 0\t%s\n" % (m.encode(), s.encode(), name) for m, s, name in entries)
        self.run("update-index", "--index-info", inp=rows, env={"GIT_INDEX_FILE": idx})
        return self.run("write-tree", env={"GIT_INDEX_FILE": idx})

    def commit(self, tree, parents, when):
        args = ["commit-tree", tree]
        for p in parents:
            args += ["-p", p]
        return self.run(*args, "-m", "fixture", env={"GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when})


class ListedReads(unittest.TestCase):
    """A read that fails on a path the tree lists is UNKNOWN, never empty text. absent() must hold for
    three shapes: a path that starts with a colon (ls-tree reads it as pathspec magic); a non-UTF-8 name
    (it must be read byte for byte; a name that misses on every revision is no clean verdict); and a
    gitlink (not a blob: its text is "", and reading it is no failure)."""
    T0, T1, T2, T3 = "2025-12-01T10:00:00", "2026-01-01T10:00:00", "2026-01-02T10:00:00", "2026-01-03T10:00:00"

    def repo(self):
        r = Repo()
        return r, Plumb(r)

    def test_a_failed_read_of_a_colon_path_is_unknown(self):
        r, p = self.repo()
        app, name = p.blob(["app"]), b":/X"
        base = p.commit(p.tree([("100644", app, b"app.txt"), ("100644", p.blob(["1", "2", "3"]), name)]), [], self.T0)
        lane = p.commit(p.tree([("100644", app, b"app.txt"), ("100644", p.blob(["1 lane", "2", "3"]), name)]), [base], self.T1)
        main = p.commit(p.tree([("100644", app, b"app.txt"), ("100644", p.blob(["1", "2", "3", "main added"]), name)]), [base], self.T2)
        merged = p.commit(p.tree([("100644", app, b"app.txt"), ("100644", p.blob(["1 lane", "2", "3", "main added"]), name)]), [lane, main], self.T3)
        r.sh("update-ref", "refs/remotes/origin/main", main)
        with FailReads(merged, ":/X").armed():
            with self.assertRaises(C.Unknown):
                C.check(r.dir, "origin/main", merged)

    def test_a_drop_in_a_non_utf8_tracked_name_is_never_clean(self):
        r, p = self.repo()
        app, name = p.blob(["app"]), b"caf\xe9.txt"
        base = p.commit(p.tree([("100644", app, b"app.txt"), ("100644", p.blob(["x", "y", "z"]), name)]), [], self.T0)
        lane = p.commit(p.tree([("100644", app, b"app.txt"), ("100644", p.blob(["x", "y", "z", "lane line"]), name)]), [base], self.T1)
        main = p.commit(p.tree([("100644", app, b"app.txt"), ("100644", p.blob(["x", "y", "z", "main line"]), name)]), [base], self.T2)
        merged = p.commit(p.tree([("100644", app, b"app.txt"), ("100644", p.blob(["x", "y", "z", "lane line"]), name)]), [lane, main], self.T3)
        r.sh("update-ref", "refs/remotes/origin/main", main)
        try:
            bad, _ = C.check(r.dir, "origin/main", merged)
        except C.Unknown:
            return  # a read that cannot run is UNKNOWN: a verdict, not clean
        self.assertTrue(any("drops" in x and "main line" in x for x in bad), "clean: the merge drops main's line and the check missed it")

    def test_a_gitlink_with_an_absent_commit_is_not_unknown(self):
        r, p = self.repo()
        app = p.blob(["app"])
        pin = lambda sha: ("160000", sha, b"sub")
        base = p.commit(p.tree([("100644", app, b"app.txt"), pin("1" * 40)]), [], self.T0)
        lane = p.commit(p.tree([("100644", app, b"app.txt"), pin("3" * 40)]), [base], self.T1)
        main = p.commit(p.tree([("100644", app, b"app.txt"), pin("2" * 40)]), [base], self.T2)
        merged = p.commit(p.tree([("100644", app, b"app.txt"), pin("4" * 40)]), [lane, main], self.T3)
        r.sh("update-ref", "refs/remotes/origin/main", main)
        got = C.check(r.dir, "origin/main", merged)
        self.assertEqual(got[0], [], "a gitlink reads as empty text: no drop, no Unknown")


class PrintedFindings(unittest.TestCase):
    """main() prints each finding. A non-UTF-8 name reaches the print as text with surrogates, which a strict
    stream cannot encode: the print raised, and the finding was lost. Each run, under a strict cp1252 stream
    and a strict utf-8 stream, must print a readable finding that names the file, with no traceback, and exit
    with its normal code: 1 for a FAIL, 0 for an UNKNOWN (CI unset) and for --history."""

    ENCODINGS = ("cp1252", "utf-8")
    T0, T1, T2, T3 = ListedReads.T0, ListedReads.T1, ListedReads.T2, ListedReads.T3

    def drop_repo(self):
        """The non-UTF-8 drop: main's line is in the file on main, and the merge drops it. -> (repo, merge sha)."""
        r = Repo()
        p = Plumb(r)
        app, name = p.blob(["app"]), b"caf\xe9.txt"
        base = p.commit(p.tree([("100644", app, b"app.txt"), ("100644", p.blob(["x", "y", "z"]), name)]), [], self.T0)
        lane = p.commit(p.tree([("100644", app, b"app.txt"), ("100644", p.blob(["x", "y", "z", "lane line"]), name)]), [base], self.T1)
        main = p.commit(p.tree([("100644", app, b"app.txt"), ("100644", p.blob(["x", "y", "z", "main line"]), name)]), [base], self.T2)
        merged = p.commit(p.tree([("100644", app, b"app.txt"), ("100644", p.blob(["x", "y", "z", "lane line"]), name)]), [lane, main], self.T3)
        r.sh("update-ref", "refs/remotes/origin/main", main)
        return r, merged

    def run_main(self, argv, encoding, env=None):
        """main(argv) with stdout a strict stream of `encoding`. -> (rc, what was printed). A raise is a failure.
        env: name -> value set for the run, None pops the name."""
        out = io.TextIOWrapper(io.BytesIO(), encoding=encoding, errors="strict", newline="\n")
        with unittest.mock.patch.dict(os.environ), contextlib.redirect_stdout(out):
            os.environ.pop("CI", None)
            for name, value in (env or {}).items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
            try:
                rc = C.main(argv)
            except Exception as e:  # the traceback is the failure
                self.fail("main raised %s under %s: %s" % (type(e).__name__, encoding, e))
        out.flush()
        return rc, out.buffer.getvalue().decode(encoding, "replace")

    def test_a_fail_prints_a_readable_finding_and_exits_1(self):
        r, merged = self.drop_repo()
        for enc in self.ENCODINGS:
            with self.subTest(encoding=enc):
                rc, text = self.run_main(["--upstream", "origin/main", "--head", merged, "--repo", r.dir], enc)
                self.assertEqual(rc, 1)
                self.assertIn("FAIL", text)
                self.assertIn("caf", text)
                self.assertIn(".txt", text)
                self.assertIn("main line", text)

    def test_an_unknown_prints_a_readable_finding_and_exits_0(self):
        r, merged = self.drop_repo()
        fault = FailReads(merged, "caf\udce9.txt")  # the read of the name fails: UNKNOWN, the name is not UTF-8
        for enc in self.ENCODINGS:
            with self.subTest(encoding=enc), fault.armed():
                rc, text = self.run_main(["--upstream", "origin/main", "--head", merged, "--repo", r.dir], enc)
                self.assertEqual(rc, 0)
                self.assertIn("UNKNOWN", text)
                self.assertIn("caf", text)
                self.assertIn(".txt", text)
        self.assertGreater(fault.hits, 0, "the faulted read never ran")

    def test_history_prints_a_readable_finding_and_exits_0(self):
        r, merged = self.drop_repo()
        for enc in self.ENCODINGS:
            with self.subTest(encoding=enc):
                rc, text = self.run_main(["--history", merged, "--repo", r.dir], enc)
                self.assertEqual(rc, 0)
                self.assertIn("drops", text)
                self.assertIn("caf", text)
                self.assertIn(".txt", text)


class BodyReadFails:
    """A `git log` that reads the commit message body (%B or %b) exits 128 while the block is armed. That is the hint's
    read: allowed() reads trailers only, and the scan reads subjects. Other reads are real. `hits` counts the failures."""

    def __init__(self):
        self.hits, self.real_run = 0, subprocess.run

    def run(self, args, *a, **k):
        if "log" in args and any(x.startswith("--format=") and ("%B" in x or "%b" in x) for x in args):
            self.hits += 1
            return subprocess.CompletedProcess(args, 128, "", "fatal: injected read failure")
        return self.real_run(args, *a, **k)

    def armed(self):
        return unittest.mock.patch.object(subprocess, "run", self.run)


class SpawnCount:
    """Counts the `git` processes started while the block is armed. Every spawn, `subprocess.run` too, goes through Popen,
    so Popen is the one place counted. A count, never a clock."""

    def __init__(self):
        self.n, self.real = 0, subprocess.Popen

    def popen(self, args, *a, **k):
        if list(args)[:1] == ["git"]:
            self.n += 1
        return self.real(args, *a, **k)

    def armed(self):
        return unittest.mock.patch.object(subprocess, "Popen", self.popen)


class DropsLinesHint(unittest.TestCase):
    """A `Drops-lines:` line that git does not parse as a trailer (it is not in the last paragraph) excuses nothing.
    A refusal names the commit and says where the trailer goes. The hint never excuses a finding, and it shows
    only beside a finding: a misplaced line with no finding prints nothing (no hint and no note). Where check() puts the
    hint (problems or notes) is not pinned: each case reads both, and the printed cases read the output."""

    HINT = "not as a trailer"
    CO = "Co-Authored-By: Someone <someone@example.com>"
    WHY = "Drops-lines: app.txt -- the owner wants Card back"
    ABOVE = "Bring Card back\n\n%s\n\n%s" % (WHY, CO)  # its own paragraph above Co-Authored-By
    IN_BODY = "Bring Card back\n\nWhy:\n%s\nthe rest of the why\n\n%s" % (WHY, CO)  # a line inside a body paragraph
    RIGHT = "Bring Card back\n\nWhy.\n\n%s\n%s" % (WHY, CO)  # one last paragraph: git parses it
    run_main = PrintedFindings.run_main

    def setUp(self):
        self.r = base_repo()

    def land_pr(self, msg="delete Card"):
        """PR 1 deletes Card from app.txt, and lands on main with a merge commit. `msg` is the message of its commit."""
        r = self.r
        r.sh("checkout", "-q", "-b", "pr1")
        r.commit(msg, app_txt=BODY)
        r.sh("checkout", "-q", "main")
        r.sh("merge", "-q", "--no-ff", "-m", "Merge pull request #1", "pr1")
        r.push()

    def revert_with(self, msg):
        """Branch `oops`: revert PR 1 (a finding on app.txt), reword that commit to `msg`, then add a plain commit on top.
        -> the sha of the reworded commit. HEAD is the plain one, so the hint must name the right commit, not the last."""
        r = self.r
        r.sh("checkout", "-q", "-b", "oops")
        r.sh("revert", "--no-edit", "-m", "1", "main")
        r.sh("commit", "-q", "--amend", "-m", msg)
        sha = r.sh("rev-parse", "HEAD")
        r.commit("tidy other", other_txt="other v2\n")
        return sha

    def parsed(self, sha):
        return self.r.sh("log", "-1", "--no-show-signature", "--format=%(trailers:key=Drops-lines,valueonly)", sha).strip()

    def said(self):
        """-> (problems, every line check() says: problems and notes)."""
        got = self.r.verdict()
        return got, "\n".join(got + self.r.notes)

    def assertHintFor(self, sha, text):
        self.assertTrue(any(sha[:7] in l and self.HINT in l for l in text.splitlines()), text)  # one line: the sha and the hint
        self.assertIn("last paragraph", text)

    def assertRefusedWithHint(self, sha, got, text):
        self.assertEqual(self.parsed(sha), "", "fixture: git must not parse the line as a trailer")
        self.assertTrue(any("app.txt" in p for p in got), got)  # the refusal holds
        self.assertHintFor(sha, text)
        self.assertNotIn(self.r.sh("rev-parse", "HEAD")[:7], text)  # the culprit, not the head

    def test_a_misplaced_line_in_any_paragraph_is_refused_with_a_hint(self):
        """Rows: the line in its own paragraph above Co-Authored-By, and a line inside a body paragraph."""
        for msg in (self.ABOVE, self.IN_BODY):
            with self.subTest(msg=msg):
                self.r = base_repo()
                self.land_pr()
                sha = self.revert_with(msg)
                got, text = self.said()
                self.assertRefusedWithHint(sha, got, text)

    def test_a_trailer_that_parses_is_excused_with_no_hint(self):
        self.land_pr()
        sha = self.revert_with(self.RIGHT)
        self.assertEqual(self.parsed(sha), "app.txt -- the owner wants Card back", "fixture: git must parse the trailer")
        got, text = self.said()
        self.assertEqual(got, [])
        self.assertEqual(self.r.notes, ["ALLOWED app.txt: the owner wants Card back"])
        # The CLI on the same repo: exit 0, the ALLOWED line, no hint.
        rc, out = self.run_main(["--upstream", "origin/main", "--head", "HEAD", "--repo", self.r.dir], "utf-8")
        self.assertEqual(rc, 0)
        self.assertIn("ALLOWED app.txt", out)
        self.assertNotIn(self.HINT, out)

    def test_a_trailer_with_no_reason_keeps_the_finding_and_gets_no_hint(self):
        """git returns it, so placement is right: the missing reason is the fault, and a placement hint would be wrong.
        Rows: a bare path with and without Co-Authored-By below it, and an empty value."""
        for msg in ("Bring Card back\n\nDrops-lines: app.txt\n%s" % self.CO,
                    "Bring Card back\n\nDrops-lines: app.txt",
                    "Bring Card back\n\nDrops-lines:\n%s" % self.CO):
            with self.subTest(msg=msg):
                self.r = base_repo()
                self.land_pr()
                sha = self.revert_with(msg)
                self.assertTrue(self.r.sh("log", "-1", "--format=%(trailers:key=Drops-lines)", sha).startswith("Drops-lines:"),
                                "fixture: git must parse the trailer")
                got, text = self.said()
                self.assertTrue(any("app.txt" in p for p in got), got)
                self.assertNotIn(self.HINT, text)

    def test_a_misplaced_line_with_no_finding_prints_nothing(self):
        """Chosen: no hint and no note. The line costs nothing when the check is green."""
        r = self.r
        r.sh("checkout", "-q", "-b", "quiet")
        sha = r.commit(self.ABOVE, other_txt="other v2\n")
        self.assertEqual(self.parsed(sha), "", "fixture: git must not parse the line as a trailer")
        got, text = self.said()
        self.assertEqual(got, [])
        self.assertEqual(r.notes, [])

    def test_a_mid_line_mention_of_the_word_gets_no_hint(self):
        """Only a line that starts with `Drops-lines:` counts. A message that talks about the word is not a mistake."""
        self.land_pr()
        self.revert_with("Explain Drops-lines: the check reads trailers\n\nWe say Drops-lines: app.txt -- x in prose.\n\n%s" % self.CO)
        got, text = self.said()
        self.assertTrue(any("app.txt" in p for p in got), got)
        self.assertNotIn(self.HINT, text)

    def test_a_misplaced_line_on_a_commit_already_on_main_gets_no_hint(self):
        """The scanned range is upstream..head. A commit main already holds is not the author's to fix."""
        self.land_pr(self.ABOVE)
        self.revert_with("Bring Card back")
        got, text = self.said()
        self.assertTrue(any("app.txt" in p for p in got), got)
        self.assertNotIn(self.HINT, text)

    def test_main_prints_the_hint_and_still_exits_1(self):
        self.land_pr()
        sha = self.revert_with(self.ABOVE)
        rc, text = self.run_main(["--upstream", "origin/main", "--head", "HEAD", "--repo", self.r.dir], "utf-8")
        self.assertEqual(rc, 1)
        self.assertIn("FAIL", text)
        self.assertTrue(any(l.startswith("silent-undo:") and sha[:7] in l and self.HINT in l for l in text.splitlines()), text)
        self.assertIn("last paragraph", text)

    def test_the_merge_tool_refusal_carries_the_hint(self):
        import merge
        self.land_pr()
        sha = self.revert_with(self.ABOVE)
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(merge.Stop) as cm:
            merge.undo_check(self.r.dir, "origin/main")
        text = out.getvalue() + "\n" + str(cm.exception)
        self.assertIn("app.txt", str(cm.exception))  # the refusal holds
        self.assertTrue(any(sha[:7] in l and self.HINT in l for l in text.splitlines()), text)

    # ------------------------------------------------ reads of the message

    def test_a_folded_parsed_trailer_does_not_hide_a_misplaced_line(self):
        """A trailer value folded onto a continuation line is one trailer. It must not pass for a second Drops-lines line."""
        self.land_pr()
        sha = self.revert_with("Bring Card back\n\nDrops-lines: app.txt -- wrong place\n\n"
                               "Drops-lines: other.txt -- reason that\n continues here\n%s" % self.CO)
        got_trailer = self.parsed(sha)
        self.assertIn("other.txt", got_trailer, "fixture: git must parse the folded trailer")
        self.assertIn("continues here", got_trailer, "fixture: git must fold the continuation into it")
        got, text = self.said()
        self.assertTrue(any("app.txt" in p for p in got), got)  # the refusal holds
        self.assertHintFor(sha, text)

    def test_a_control_byte_in_the_body_does_not_hide_a_misplaced_line(self):
        """A \\x01 byte before the line. A reader that splits records on that byte loses the commit and says nothing."""
        self.land_pr()
        sha = self.revert_with("Bring Card back\n\nWhy:\x01 a stray control byte\n\n%s\n\n%s" % (self.WHY, self.CO))
        self.assertIn("\x01", self.r.sh("log", "-1", "--format=%B", sha), "fixture: the message must hold the byte")
        self.assertEqual(self.parsed(sha), "", "fixture: git must not parse the line as a trailer")
        got, text = self.said()
        self.assertTrue(any("app.txt" in p for p in got), got)
        self.assertHintFor(sha, text)

    def misplaced_repo_with_a_failing_hint_read(self):
        """A finding on app.txt, a misplaced line on the commit, and a message read that fails. The hint is an extra: a
        failed read of it must not turn the FAIL into an UNKNOWN (exit 0 locally) or into an owner override."""
        self.land_pr()
        sha = self.revert_with(self.ABOVE)
        self.assertEqual(self.parsed(sha), "", "fixture: git must not parse the line as a trailer")
        return BodyReadFails()

    def test_main_and_the_merge_tool_still_refuse_with_the_finding_when_the_hint_read_fails(self):
        """The hint read fails. main still exits 1 with the finding, and the merge tool still refuses."""
        import merge
        fault = self.misplaced_repo_with_a_failing_hint_read()
        with fault.armed():
            rc, text = self.run_main(["--upstream", "origin/main", "--head", "HEAD", "--repo", self.r.dir], "utf-8")
        self.assertGreater(fault.hits, 0, "the faulted read never ran")
        self.assertEqual(rc, 1, text)
        self.assertIn("FAIL", text)
        self.assertIn("app.txt", text)
        before = fault.hits
        with fault.armed(), contextlib.redirect_stdout(io.StringIO()), self.assertRaises(merge.Stop) as cm:
            merge.undo_check(self.r.dir, "origin/main")
        self.assertGreater(fault.hits, before, "the faulted read never ran on the merge leg")
        self.assertIn("app.txt", str(cm.exception))

    def test_the_unknown_override_does_not_excuse_a_finding_when_the_hint_read_fails(self):
        """--undo-check-unknown-ok is the way out of an unreadable history. It never excuses a finding."""
        import merge
        fault = self.misplaced_repo_with_a_failing_hint_read()
        with fault.armed(), contextlib.redirect_stdout(io.StringIO()), self.assertRaises(merge.Stop) as cm:
            merge.undo_check(self.r.dir, "origin/main", unknown_ok="the owner accepts an unreadable history")
        self.assertGreater(fault.hits, 0, "the faulted read never ran")
        self.assertIn("app.txt", str(cm.exception))

    # ------------------------------------------------ the repo's config, and the cost of the read

    def test_a_fixed_grep_pattern_type_in_the_repo_config_does_not_hide_the_hint(self):
        """grep.patternType=fixed makes `git log --grep` read its pattern as a literal string. A hint that filters
        commits with a regex through --grep then matches none, and prints nothing."""
        self.r.sh("config", "grep.patternType", "fixed")
        self.land_pr()
        sha = self.revert_with(self.ABOVE)
        got, text = self.said()
        self.assertRefusedWithHint(sha, got, text)

    def test_a_signed_commit_with_log_show_signature_gets_the_right_sha_in_the_hint(self):
        """log.showSignature=true makes `git log` print a signature block before a signed commit's record. A read that
        lets it in shifts the sha, trailers and body fields of that commit, so the hint names a wrong sha. The culprit is
        ssh-signed here with a key made offline in the temp dir. Without ssh-keygen the case cannot be built: it skips."""
        ssh_keygen = shutil.which("ssh-keygen")
        if not ssh_keygen:
            self.skipTest("ssh-keygen is absent: a signed commit cannot be built")
        key = os.path.join(self.r.tmp.name, "k")
        subprocess.run([ssh_keygen, "-q", "-t", "ed25519", "-N", "", "-C", "t@t", "-f", key],
                       check=True, capture_output=True)
        with open(key + ".pub", encoding="utf-8") as f:
            kind, blob = f.read().split()[:2]
        signers = os.path.join(self.r.tmp.name, "signers")
        with open(signers, "w", encoding="utf-8") as f:
            f.write('t@t namespaces="git" %s %s\n' % (kind, blob))
        self.land_pr()
        # This case signs on purpose, so its git runs without the opt-out. The signer is the local ssh-keygen with the
        # key above, named here so no global signer (a cloud signing program) is ever called.
        self.r.signs = True
        for k, v in (("gpg.format", "ssh"), ("user.signingkey", key), ("gpg.ssh.allowedSignersFile", signers),
                     ("gpg.ssh.program", ssh_keygen), ("commit.gpgsign", "true"), ("log.showSignature", "true")):
            self.r.sh("config", k, v)
        sha = self.revert_with(self.ABOVE)
        self.assertEqual(self.r.sh("log", "-1", "--no-show-signature", "--format=%G?", sha), "G",
                         "fixture: the commit must carry a good signature")
        self.assertIn("Good", self.r.sh("log", "-1", "--no-patch", sha), "fixture: log.showSignature must print the block")
        got, text = self.said()
        self.assertRefusedWithHint(sha, got, text)

    def test_the_hint_costs_a_constant_number_of_git_spawns_at_fifty_candidates(self):
        """50 commits each hold a misplaced line. Reading them must not cost a git process per commit: at most 2 in all.
        A count of spawns, not a time. `misplaced` is the hint's read."""
        r = self.r
        r.sh("checkout", "-q", "-b", "many")
        for i in range(50):
            r.sh("commit", "-q", "--allow-empty", "-m", "Bring Card back %d\n\n%s\n\n%s" % (i, self.WHY, self.CO))
        fault = SpawnCount()
        with fault.armed():
            out = C.misplaced(r.dir, "origin/main..HEAD")
        self.assertIn(self.HINT, "\n".join(out), out)  # the read ran, and found the candidates
        self.assertLessEqual(fault.n, 2, "git spawns for 50 candidate commits: %d" % fault.n)


class RecordsPage(unittest.TestCase):
    """docs/records.md is excused only when it equals the generator's output for the head. Here the generator
    writes the d-one row, the debt file still stands, and a hand edit drops the row: an undo, so it is refused."""

    def test_a_page_that_differs_from_the_generator_is_still_refused(self):
        import hook_catalog as gen
        debts = "## Debts\n\n| Slug | Gist | Link |\n|---|---|---|\n"
        row = "| `d-one` | Keep the page honest. | [`debts/d-one.md`](../debts/d-one.md) |\n"
        r = base_repo()
        r.commit("records index", **{"docs/records.md": gen.RECORDS_INTRO})
        r.push()
        r.sh("checkout", "-q", "-b", "pr1")
        r.commit("add debt d-one", **{"debts/d-one.md": "**What.** Keep the page honest.\n", "docs/records.md": gen.RECORDS_INTRO + debts + row})
        r.sh("checkout", "-q", "main")
        r.sh("merge", "-q", "--no-ff", "-m", "Merge pull request #1", "pr1")
        r.push()
        r.sh("checkout", "-q", "-b", "oops")
        r.commit("drop the d-one row by hand", **{"docs/records.md": gen.RECORDS_INTRO})
        got = r.verdict()
        self.assertTrue(any("docs/records.md" in p for p in got), got)
        self.assertEqual(C.generated_page(r.dir, "HEAD", {"docs/records.md"}), ("docs/records.md", False))


    @staticmethod
    def without_debt_rows(text):
        """The layout file's text with the debts kind no longer listed on the records page."""
        layout = json.loads(text)
        assert layout["kinds"]["debts"].pop("listed") is True  # a no-op edit would make a false red
        return json.dumps(layout, indent=2) + "\n"
    KEEP = "# Keep the records index\n"
    DEBT = "**What.** Keep the page honest.\n"
    GONE = "| `d-gone` | Gone. | [`debts/d-gone.md`](../debts/d-gone.md) |\n"
    PY = dict(ENV, PYTHONDONTWRITEBYTECODE="1")  # no __pycache__ in a fixture: `git add -A` would commit it

    def put_lf(self, r, files):
        """Write files with LF endings, as the generator does. Repo.put writes the platform's endings."""
        for path, text in files.items():
            full = os.path.join(r.dir, *path.split("/"))
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)

    def commit_all(self, r, msg):
        r.sh("add", "-A")
        r.sh("commit", "-q", "-m", msg)

    def regenerate(self, r):
        """Run the repo's own generator as a person does (--records-only), and check that it wrote the page."""
        run = subprocess.run([sys.executable, os.path.join(r.dir, "lint", "hook_catalog.py"), "--records-only", "--root", r.dir],
                             cwd=r.dir, capture_output=True, text=True, env=self.PY)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("wrote docs/records.md", run.stdout, run.stdout + run.stderr)

    def fixture(self):
        """A pushed base. The checker and its generator are committed before the fork, so a later change to them is
        outside the reversal window. The debt block lands as its own insertion into a page that already exists,
        the shape the reversal check reads as an undo: a page made whole in one commit is not."""
        r = base_repo()
        self.put_lf(r, tracked_tree.read_tracked("lint", "hooks"))  # the checker, its generator and their imports
        self.put_lf(r, {"plans/keep.md": self.KEEP})
        self.regenerate(r)
        self.commit_all(r, "the checker, its generator, a plan and the records page")
        self.put_lf(r, {"debts/d-one.md": self.DEBT})
        self.regenerate(r)
        self.commit_all(r, "a debt and its row")
        r.push()
        return r

    def test_a_generator_that_drops_the_debt_rows_is_refused_when_it_regenerates_the_page(self):
        """Safety hole: a page was excused when it equalled the generator that the head ships. Here the head edits that generator
        to drop the debt rows, regenerates the page, and passes with no trailer. The fixture runs its own checker, as CI
        runs the head's checkout, so the head's generator is the oracle that the safety hole trusted."""
        r = self.fixture()
        r.sh("checkout", "-q", "-b", "oops")
        with open(os.path.join(r.dir, "lint", "layout.json"), encoding="utf-8", newline="") as f:
            text = f.read()
        self.put_lf(r, {"lint/layout.json": self.without_debt_rows(text)})
        self.regenerate(r)
        self.commit_all(r, "drop the debts from the records page")
        with open(os.path.join(r.dir, "docs", "records.md"), encoding="utf-8") as f:
            self.assertNotIn("d-one", f.read())  # the regenerated page really lost the debt row
        run = subprocess.run([sys.executable, os.path.join(r.dir, "lint", "check_silent_undo.py"), "--repo", r.dir],
                             cwd=r.dir, capture_output=True, text=True, env=self.PY)
        out = run.stdout + run.stderr
        self.assertNotIn("UNKNOWN", out, out)
        self.assertEqual(run.returncode, 1, out)
        self.assertIn("silent-undo: FAIL:", out, out)  # the debt rows vanished with no trailer: refused

    def test_a_regenerated_page_with_no_hand_edit_is_accepted(self):
        """Accepted: the head's page is the generator's output and no one typed in it. The fork commit typed a row for
        a debt with no file. Regenerating drops that row. The reversal is real, and the page's equality excuses it."""
        r = self.fixture()
        with open(os.path.join(r.dir, "docs", "records.md"), encoding="utf-8") as f:
            page = f.read()
        stale = page.replace("| `d-one`", self.GONE + "| `d-one`", 1)
        self.assertNotEqual(stale, page)  # the typed row really went in
        self.put_lf(r, {"docs/records.md": stale})
        self.commit_all(r, "type a row for a debt with no file")
        r.push()
        r.sh("checkout", "-q", "-b", "regen")
        self.regenerate(r)
        self.commit_all(r, "regenerate the records page")
        got = r.verdict()
        self.assertEqual(got, [], (got, r.notes))
        self.assertTrue(any("ALLOWED docs/records.md" in n for n in r.notes), r.notes)

    TOOL = os.path.join(HERE, "hook_catalog.py")  # the merge tool's own generator: the oracle when upstream has none

    def run_generator(self, r, path):
        """Run the generator at `path` against r as a person does (--records-only), and check that it wrote the page."""
        run = subprocess.run([sys.executable, path, "--records-only", "--root", r.dir],
                             cwd=r.dir, capture_output=True, text=True, env=self.PY)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("wrote docs/records.md", run.stdout, run.stdout + run.stderr)

    def test_a_head_generator_never_judges_the_page_when_upstream_has_none(self):
        """With no generator on the base, the page is judged by the merge tool's own
        generator. Here the base has no lint/ folder. The head ships its own generator, which drops the debt rows, and
        regenerates the page with it. The tool's generator still writes the debt row, so the head's page differs and
        is refused. If the head's generator were the oracle, the page would match it and pass."""
        r = base_repo()
        self.put_lf(r, {"plans/keep.md": self.KEEP})
        self.run_generator(r, self.TOOL)
        self.commit_all(r, "the records page, with no generator on main")
        self.put_lf(r, {"debts/d-one.md": self.DEBT})
        self.run_generator(r, self.TOOL)
        self.commit_all(r, "a debt and its row")
        r.push()
        self.assertNotIn("lint/hook_catalog.py", r.sh("ls-tree", "-r", "--name-only", "origin/main"))  # the base has no generator
        r.sh("checkout", "-q", "-b", "oops")
        head = tracked_tree.read_tracked("lint", "hooks")  # the generator and its imports; without them it crashes and fails closed
        head["lint/layout.json"] = self.without_debt_rows(head["lint/layout.json"])
        self.put_lf(r, head)
        self.run_generator(r, os.path.join(r.dir, "lint", "hook_catalog.py"))
        with open(os.path.join(r.dir, "docs", "records.md"), encoding="utf-8") as f:
            self.assertNotIn("d-one", f.read())  # the head's own page really lost the debt row
        self.commit_all(r, "drop the debts from the records page, with the generator that drops them")
        got, notes = C.check(r.dir, "origin/main", "HEAD", tool=self.TOOL)
        self.assertTrue(any("docs/records.md" in p for p in got), (got, notes))


NO_EXCUSE = "check() takes no run_state: a Retire-run cite cannot excuse a debt close (decision debt-close-runs-retire)"
CASE_BODY = "CASE_BODY"  # the env var the flag names in the CLI cases: not PR_BODY, so a build that reads PR_BODY fails them
PR_BODY = "PR_BODY"  # the env var CI and the composite action pass the PR body in


class RetireCite(unittest.TestCase):
    """A debt close is excused only by a `Retire-run: <slug> -- <run URL>` line in the PR body's last paragraph, for a run that
    is green on the PR head or above it, and only for the debt's own path (decision debt-close-runs-retire). The green case is
    the #1099 shape: a prose Retire and that cite. Each other case changes one input and must keep its finding. Each case first
    reads the same PR through the debt-close check, so its kind is known before the silent-undo verdict is read."""

    SLUG = "session-start-env-reaches-neon"
    DEBT = "docs/debts/%s.md" % SLUG
    NOTE = "docs/other/second-note.md"
    CITE = "Summary.\n\nRetire-run: %s -- %s\n"
    RED_RETIRE = "Delete the old helper. Check: `tests/test_fail.py`."
    MOVED = "docs/moved.md"
    OTHER = "docs/debts/other-debt.md"
    OTHER_SLUG = "other-debt"
    OTHER_RUN_URL = "https://github.com/fixture/repo/actions/runs/43"
    NOTE_LINE = "- **Note.** Added on main after the cut.\n"

    def setUp(self):
        self.r = base_repo()
        self.r.put(".claude/layout-extras.json", json.dumps({"kinds": {}, "rolled-out": True}) + "\n")
        self.r.put("tests/test_pass.py", "import sys\nsys.exit(0)\n")
        self.r.put("tests/test_fail.py", "import sys\nsys.exit(1)\n")
        self.r.sh("add", "-A")
        self.r.sh("commit", "-q", "-m", "base: the layout file and two test files")
        self.r.push()

    def land(self, paths):
        """A merged PR that adds `paths` ({path: text}, .md only) to main: the step Red.merged_pr makes."""
        Red.merged_pr(self, branch="landed", msg="add the files", **{p[:-3].replace("/", "__") + "_md": t for p, t in paths.items()})

    def drop(self, *paths):
        """A branch cut from main that deletes `paths`. -> its head sha."""
        self.r.sh("checkout", "-q", "-b", "retire")
        for p in paths:
            self.r.sh("rm", "-q", p)
        self.r.sh("commit", "-q", "-m", "drop the files")
        return self.r.sh("rev-parse", "HEAD")

    def assert_deleted(self, head, *paths):
        names = self.r.sh("diff", "--name-status", "-M", "origin/main", head).splitlines()
        for p in paths:
            self.assertIn("D\t" + p, names, "the PR does not delete %s, so the case proves nothing" % p)

    def cut_then_main_adds_the_note(self, retire=PROSE):
        """Cut `retire` from main, then main adds NOTE_LINE to the debt, then `retire` merges main in: it holds that line.
        The debt keeps the Retire line `retire` names, so the cut and main's debt agree on it."""
        self.r.sh("checkout", "-q", "-b", "retire")
        self.r.put("other.txt", "branch work\n")
        self.r.sh("add", "-A")
        self.r.sh("commit", "-q", "-m", "branch work")
        self.r.sh("checkout", "-q", "main")
        self.r.put(self.DEBT, debt(retire) + self.NOTE_LINE)
        self.r.sh("add", "-A")
        self.r.sh("commit", "-q", "-m", "main adds a line to the debt")
        self.r.push()
        self.r.sh("checkout", "-q", "retire")
        self.r.sh("merge", "-q", "--no-edit", "origin/main")

    def drop_note(self, path):
        full = os.path.join(self.r.dir, path)
        with open(full) as f:
            text = f.read()
        self.assertIn(self.NOTE_LINE, text, "the branch does not hold main's line, so the case proves nothing")
        self.r.put(path, text.replace(self.NOTE_LINE, ""))

    def two_cited_closes(self, retire=PROSE):
        """Two debts. DEBT: landed by a PR, then main adds NOTE_LINE after the cut; the branch deletes it, so the delete undoes
        main's line and has a finding with no cite. OTHER: on main with no PR, so its delete has no finding. Both are cited."""
        self.r.put(self.OTHER, debt("Delete the other helper once nothing reads it."))
        self.r.sh("add", "-A")
        self.r.sh("commit", "-q", "-m", "add the other debt on main with no PR")
        self.r.push()
        self.land({self.DEBT: debt(retire)})
        self.cut_then_main_adds_the_note(retire)
        self.r.sh("rm", "-q", self.DEBT, self.OTHER)
        self.r.sh("commit", "-q", "-m", "delete both debts")
        head = self.r.sh("rev-parse", "HEAD")
        self.assert_deleted(head, self.DEBT, self.OTHER)
        body = (self.CITE % (self.SLUG, RUN_URL)) + ("Retire-run: %s -- %s\n" % (self.OTHER_SLUG, self.OTHER_RUN_URL))
        return head, body

    def scope(self, head, body, runs):
        """(slug, kind) of each close the debt-close check gives this PR: the kind the case is about."""
        return sorted((f.slug, f.kind) for f in D.check(self.r.dir, "origin/main", head, pr_body=body, run_state=runs))

    def silent(self, head, body="", runs=None, strict=False):
        """(problems, notes) of the silent-undo check on `head`, cited by `body` with the reader `runs`.
        strict: the case needs the excuse, so check() must take run_state; a missing parameter is a named red.
        Otherwise the reader is passed only when check() takes it, so on a check without the parameter the case
        reads the finding it keeps."""
        params = inspect.signature(C.check).parameters
        if strict:
            self.assertIn("run_state", params, NO_EXCUSE)
        kw = {"run_state": runs} if "run_state" in params else {}
        return C.check(self.r.dir, "origin/main", head, pr_body=body, **kw)

    @staticmethod
    def finding(problems, path):
        return [p for p in problems if p.startswith(path + ":")]

    @staticmethod
    def allowed(notes):
        return [n for n in notes if n.startswith("ALLOWED ")]

    def assert_not_accepted(self, notes, fact, label):
        """The one cite line for the flagged debt says its cite was not accepted, and the reason holds `fact`."""
        lines = [n for n in notes if n.startswith("cite for ")]
        prefix = "cite for %s not accepted: " % self.SLUG
        self.assertEqual(len(lines), 1, "%s: want one 'cite for' line, got %r" % (label, notes))
        self.assertTrue(lines[0].startswith(prefix), "%s: the line does not name the slug and the verdict: %s" % (label, lines[0]))
        self.assertIn(fact, lines[0], "%s: the reason does not hold %r: %s" % (label, fact, lines[0]))

    def assert_no_cite_line(self, notes, label):
        """No cite line at all: no cite in the body, or a cite for a debt that is not flagged, or an accepted cite."""
        self.assertEqual([n for n in notes if n.startswith("cite for ")], [], "%s: a cite line was printed: %r" % (label, notes))

    def test_green_cite_on_a_prose_retire_excuses_the_debt_delete(self):
        """The #1099 shape: the debt's Retire names no test, and the PR body's last paragraph cites a green run on the head."""
        self.land({self.DEBT: debt(PROSE)})
        head = self.drop(self.DEBT)
        self.assert_deleted(head, self.DEBT)
        body = self.CITE % (self.SLUG, RUN_URL)
        self.assertEqual(self.scope(head, body, Runs(("success", head))), [], "scope: the debt-close check does not clear this close")
        problems, notes = self.silent(head, body, Runs(("success", head)), strict=True)
        self.assertEqual(problems, [], (problems, notes))
        self.assertEqual(len(self.allowed(notes)), 1, notes)
        self.assertTrue(self.allowed(notes)[0].startswith("ALLOWED %s:" % self.DEBT), notes)
        self.assert_no_cite_line(notes, "accepted cite")  # control: an accepted cite prints ALLOWED, never a not-accepted line
        _, bare_notes = self.silent(head)
        self.assert_no_cite_line(bare_notes, "no cite")  # control: no cite in the body, no cite line

    def test_a_cite_for_another_slug_does_not_excuse_the_debt_delete(self):
        self.land({self.DEBT: debt(PROSE)})
        head = self.drop(self.DEBT)
        self.assert_deleted(head, self.DEBT)
        body = self.CITE % ("another-slug", RUN_URL)
        self.assertEqual(self.scope(head, body, Runs(("success", head))), [(self.SLUG, "prose")], "scope")
        problems, notes = self.silent(head, body, Runs(("success", head)))
        self.assertTrue(self.finding(problems, self.DEBT), (problems, notes))
        self.assert_no_cite_line(notes, "another slug")  # control: the flagged debt is not cited, so no line names it

    def test_a_cited_run_that_failed_does_not_excuse_the_debt_delete(self):
        self.land({self.DEBT: debt(PROSE)})
        head = self.drop(self.DEBT)
        self.assert_deleted(head, self.DEBT)
        body = self.CITE % (self.SLUG, RUN_URL)
        self.assertEqual(self.scope(head, body, Runs(("failure", head))), [(self.SLUG, "red")], "scope")
        problems, notes = self.silent(head, body, Runs(("failure", head)))
        self.assertTrue(self.finding(problems, self.DEBT), (problems, notes))
        self.assert_not_accepted(notes, "ended failure", "failed run")

    def test_a_green_run_below_the_pr_head_does_not_excuse_the_debt_delete(self):
        self.land({self.DEBT: debt(PROSE)})
        head = self.drop(self.DEBT)
        self.assert_deleted(head, self.DEBT)
        body = self.CITE % (self.SLUG, RUN_URL)
        below = self.r.sh("rev-parse", "origin/main")  # the parent of the PR head: an ancestor, not a commit at or above it
        self.assertEqual(self.scope(head, body, Runs(("success", below))), [(self.SLUG, "red")], "scope")
        problems, notes = self.silent(head, body, Runs(("success", below)))
        self.assertTrue(self.finding(problems, self.DEBT), (problems, notes))
        self.assert_not_accepted(notes, below[:9], "run below the head")

    def test_no_run_reader_excuses_nothing(self):
        self.land({self.DEBT: debt(PROSE)})
        head = self.drop(self.DEBT)
        self.assert_deleted(head, self.DEBT)
        body = self.CITE % (self.SLUG, RUN_URL)
        self.assertEqual(self.scope(head, body, None), [(self.SLUG, "unknown")], "scope")
        problems, notes = self.silent(head, body, None)  # no run_state: the default, so the case passes the argument only if check() takes one
        self.assertTrue(self.finding(problems, self.DEBT), (problems, notes))
        self.assert_not_accepted(notes, "no reader", "no run reader")

    def test_a_run_reader_that_raises_excuses_nothing(self):
        self.land({self.DEBT: debt(PROSE)})
        head = self.drop(self.DEBT)
        self.assert_deleted(head, self.DEBT)
        body = self.CITE % (self.SLUG, RUN_URL)
        boom = RuntimeError("the run read failed: HTTP 502")
        self.assertEqual(self.scope(head, body, Runs(boom)), [(self.SLUG, "unknown")], "scope")
        problems, notes = self.silent(head, body, Runs(boom))
        self.assertTrue(self.finding(problems, self.DEBT), (problems, notes))
        self.assert_not_accepted(notes, "HTTP 502", "reader raises")

    def test_a_green_cite_does_not_excuse_a_retire_test_that_fails(self):
        self.land({self.DEBT: debt(self.RED_RETIRE)})
        head = self.drop(self.DEBT)
        self.assert_deleted(head, self.DEBT)
        body = self.CITE % (self.SLUG, RUN_URL)
        self.assertEqual(self.scope(head, body, Runs(("success", head))), [(self.SLUG, "red")], "scope")
        problems, notes = self.silent(head, body, Runs(("success", head)))
        self.assertTrue(self.finding(problems, self.DEBT), (problems, notes))
        self.assert_not_accepted(notes, "tests/test_fail.py exited 1", "red retire with a green cite")

    def test_a_cite_matching_a_deleted_non_debt_file_does_not_excuse_it(self):
        self.land({self.NOTE: "A note.\n"})
        head = self.drop(self.NOTE)
        self.assert_deleted(head, self.NOTE)
        body = self.CITE % (os.path.basename(self.NOTE)[:-3], RUN_URL)
        self.assertEqual(self.scope(head, body, Runs(("success", head))), [], "scope: no debt closes in this PR")
        problems, notes = self.silent(head)  # no cite: the deletion is a finding on its own
        self.assertTrue(self.finding(problems, self.NOTE), (problems, notes))
        problems, notes = self.silent(head, body, Runs(("success", head)))
        self.assertTrue(self.finding(problems, self.NOTE), (problems, notes))
        self.assertEqual(self.allowed(notes), [], notes)

    def test_a_cite_matching_the_deleted_debts_notes_file_does_not_excuse_it(self):
        self.land({"docs/debts/notes.md": "# Notes\n\n- A note.\n"})
        head = self.drop("docs/debts/notes.md")
        self.assert_deleted(head, "docs/debts/notes.md")
        body = self.CITE % ("notes", RUN_URL)
        self.assertEqual(self.scope(head, body, Runs(("success", head))), [], "scope: the notes file is not a debt")
        problems, notes = self.silent(head)
        self.assertTrue(self.finding(problems, "docs/debts/notes.md"), (problems, notes))
        problems, notes = self.silent(head, body, Runs(("success", head)))
        self.assertTrue(self.finding(problems, "docs/debts/notes.md"), (problems, notes))
        self.assertEqual(self.allowed(notes), [], notes)

    def test_a_cite_in_an_earlier_paragraph_does_not_excuse_the_debt_delete(self):
        self.land({self.DEBT: debt(PROSE)})
        head = self.drop(self.DEBT)
        self.assert_deleted(head, self.DEBT)
        body = "Retire-run: %s -- %s\n\nA later paragraph that cites nothing.\n" % (self.SLUG, RUN_URL)
        self.assertEqual(self.scope(head, body, Runs(("success", head))), [(self.SLUG, "prose")], "scope")
        problems, notes = self.silent(head, body, Runs(("success", head)))
        self.assertTrue(self.finding(problems, self.DEBT), (problems, notes))

    def test_the_debt_delete_is_excused_and_a_second_deleted_file_stays(self):
        self.land({self.DEBT: debt(PROSE), self.NOTE: "A note.\n"})
        head = self.drop(self.DEBT, self.NOTE)
        self.assert_deleted(head, self.DEBT, self.NOTE)
        body = self.CITE % (self.SLUG, RUN_URL)
        self.assertEqual(self.scope(head, body, Runs(("success", head))), [], "scope: the debt close is cleared")
        problems, notes = self.silent(head, body, Runs(("success", head)), strict=True)
        self.assertEqual(self.finding(problems, self.DEBT), [], (problems, notes))
        self.assertTrue(self.finding(problems, self.NOTE), (problems, notes))
        self.assertTrue(any(n.startswith("ALLOWED %s:" % self.DEBT) for n in notes), notes)

    def test_a_rename_out_of_the_debts_folder_that_drops_a_main_line_keeps_its_finding(self):
        self.land({self.DEBT: debt(PROSE)})
        self.cut_then_main_adds_the_note()
        self.r.sh("mv", self.DEBT, self.MOVED)
        self.drop_note(self.MOVED)
        self.r.sh("add", "-A")
        self.r.sh("commit", "-q", "-m", "rename the debt out and drop the main line")
        head = self.r.sh("rev-parse", "HEAD")
        names = self.r.sh("diff", "--name-status", "-M", "origin/main", head)
        self.assertIn("\t%s\t%s" % (self.DEBT, self.MOVED), names, "the PR does not rename the debt out, so the case proves nothing")
        body = self.CITE % (self.SLUG, RUN_URL)
        self.assertEqual(self.scope(head, body, Runs(("success", head))), [], "scope: the debt-close check clears this rename")
        problems, notes = self.silent(head, body, Runs(("success", head)), strict=True)
        self.assertTrue(self.finding(problems, self.DEBT), "the cite excused a rename out of docs/debts that drops a main line: "
                        "only a whole delete is excused (problems %r, notes %r)" % (problems, notes))

    def test_a_rename_out_of_the_debts_folder_that_drops_a_main_line_has_a_finding_with_no_cite(self):  # control
        self.land({self.DEBT: debt(PROSE)})
        self.cut_then_main_adds_the_note()
        self.r.sh("mv", self.DEBT, self.MOVED)
        self.drop_note(self.MOVED)
        self.r.sh("add", "-A")
        self.r.sh("commit", "-q", "-m", "rename the debt out and drop the main line")
        head = self.r.sh("rev-parse", "HEAD")
        problems, notes = self.silent(head)
        self.assertTrue(self.finding(problems, self.DEBT), (problems, notes))

    def test_only_the_close_with_a_finding_has_its_run_read(self):
        head, body = self.two_cited_closes()
        self.assertEqual(self.scope(head, body, Runs(("success", head))), [], "scope: both debt closes are cleared")
        bare, _ = self.silent(head)
        self.assertTrue(self.finding(bare, self.DEBT), "premise: the debt's delete undoes main's line, so it has a finding with no cite")
        self.assertEqual(self.finding(bare, self.OTHER), [], "premise: the debt main added with no PR has no finding")
        flagged = Runs(("success", head))
        problems, notes = self.silent(head, body, flagged, strict=True)
        self.assertEqual(self.finding(problems, self.DEBT), [], (problems, notes))
        self.assertEqual(flagged.urls, [RUN_URL], "run_state read a cited run for a close with no silent-undo finding")

    def test_the_close_with_a_finding_still_has_its_own_run_read(self):  # control
        head, body = self.two_cited_closes()
        flagged = Runs(("success", head))
        self.silent(head, body, flagged, strict=True)
        self.assertIn(RUN_URL, flagged.urls, "the close with the finding did not read its own cited run")

    def cited_close(self):
        """The #1099 shape as CI sees it: a debt landed by a PR and deleted on the branch, with a green cite in the body. -> (head, body)."""
        self.land({self.DEBT: debt(PROSE)})
        head = self.drop(self.DEBT)
        self.assert_deleted(head, self.DEBT)
        return head, self.CITE % (self.SLUG, RUN_URL)

    def cli(self, head, runs, flag=True, env=None):
        """main() on `head` as CI runs it: `--pr-body-env CASE_BODY` when flag is set, the merge tool's Host.cited_run as the run
        reader `runs` (a Runs fake), and `env` for the run's variables. PR_BODY, CASE_BODY and CI start unset. -> (exit code, printed text).
        A build without the flag exits through argparse: that is a named failure here, not a crash."""
        import merge  # lazy: merge.Host holds the one run read, reached through the ../merge path inserted at the top
        argv = ["--repo", self.r.dir, "--upstream", "origin/main", "--head", head]
        if flag:
            argv += ["--pr-body-env", CASE_BODY]
        out = io.StringIO()
        with unittest.mock.patch.dict(os.environ), contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(out):
            for name in (PR_BODY, CASE_BODY, "CI"):
                os.environ.pop(name, None)
            os.environ.update(env or {})
            with unittest.mock.patch.object(merge.Host, "cited_run", lambda host, url: runs(url)):
                try:
                    code = C.main(argv)
                except SystemExit as e:
                    self.fail("main() refuses %s (exit %s): the CLI takes no PR body yet" % (" ".join(argv[-2:]), e.code))
        return code, out.getvalue()

    def test_the_flag_reads_the_body_and_its_run_and_excuses_the_debt_delete(self):
        head, body = self.cited_close()
        self.assertEqual(self.scope(head, body, Runs(("success", head))), [], "scope: the debt-close check does not clear this close")
        runs = Runs(("success", head))
        code, out = self.cli(head, runs, env={CASE_BODY: body})
        self.assertIn(RUN_URL, runs.urls, "the run reader was not asked for the cited run, so the excuse was never read")
        self.assertIn("ALLOWED %s:" % self.DEBT, out, "no ALLOWED line for the debt delete:\n" + out)
        self.assertEqual(code, 0, out)

    def test_the_run_is_read_against_the_head_the_flag_gives(self):
        head, body = self.cited_close()
        below = self.r.sh("rev-parse", "origin/main")  # the parent of the head: a green run there excuses nothing
        self.r.sh("checkout", "-q", "--detach", below)  # the checkout is not the head, so a reader keyed to HEAD reads this run
        self.assertNotEqual(self.r.sh("rev-parse", "HEAD"), head, "premise: the checkout must not sit at the head")
        runs = Runs(("success", below))
        code, out = self.cli(head, runs, env={CASE_BODY: body})
        self.assertIn(RUN_URL, runs.urls, "the run reader was not asked for the cited run, so the case proves nothing")
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL: %s:" % self.DEBT, out, "the green run below the head excused the debt delete:\n" + out)

    def test_the_flag_with_no_body_excuses_nothing(self):
        head, body = self.cited_close()
        for label, env in (("unset", {PR_BODY: body}), ("empty", {CASE_BODY: "", PR_BODY: body})):  # PR_BODY holds the cite: it must not be read
            with self.subTest(label):
                runs = Runs(("success", head))
                code, out = self.cli(head, runs, env=env)
                self.assertEqual(runs.urls, [], "the run reader was asked with no body in %s: there is no cite to read" % CASE_BODY)
                self.assertEqual(code, 1, out)
                self.assertIn("FAIL: %s:" % self.DEBT, out, "the debt delete was excused with no body in %s:\n%s" % (CASE_BODY, out))

    def test_the_cli_run_reader_that_raises_excuses_nothing(self):
        head, body = self.cited_close()
        runs = Runs(RuntimeError("the run read failed: HTTP 502"))
        code, out = self.cli(head, runs, env={CASE_BODY: body})
        self.assertIn(RUN_URL, runs.urls, "the cited run was never read, so the case proves nothing")
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL: %s:" % self.DEBT, out, "a failed run read excused the debt delete:\n" + out)

    def test_a_drops_lines_line_in_the_env_body_excuses_its_path(self):
        head, _ = self.cited_close()
        drops = "Drops-lines: %s -- the owner retired this debt by hand\n" % self.DEBT
        runs = Runs(("success", head))
        code, out = self.cli(head, runs, env={CASE_BODY: drops})
        self.assertEqual(runs.urls, [], "premise: the body names no run, so only the Drops-lines line can excuse the delete")
        self.assertIn("ALLOWED %s:" % self.DEBT, out, "no ALLOWED line for the Drops-lines line in the body:\n" + out)
        self.assertEqual(code, 0, out)

    def test_the_same_drops_lines_line_without_the_flag_excuses_nothing(self):  # control
        head, _ = self.cited_close()
        drops = "Drops-lines: %s -- the owner retired this debt by hand\n" % self.DEBT
        code, out = self.cli(head, Runs(("success", head)), flag=False, env={CASE_BODY: drops, PR_BODY: drops})  # PR_BODY too: no default may read it
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL: %s:" % self.DEBT, out, "the body excused the delete with no flag:\n" + out)

    def test_without_the_flag_the_body_and_the_run_are_not_read(self):  # control
        head, body = self.cited_close()
        runs = Runs(("success", head))
        code, out = self.cli(head, runs, flag=False, env={CASE_BODY: body, PR_BODY: body})  # PR_BODY too: no default may read it
        self.assertEqual(runs.urls, [], "the run reader was asked with no flag: the CLI must read no run")
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL: %s:" % self.DEBT, out, "the cited delete was excused with no flag:\n" + out)

    def test_an_unread_cite_prints_one_named_line_and_still_fails(self):
        import merge  # lazy, as in cli(): the Host is the one whose construction fails in the second case
        head, body = self.cited_close()

        def no_host(host, *args, **kw):
            raise RuntimeError("merge cannot build the Host")

        with self.subTest("the read raises"):
            raising = Runs(RuntimeError("the run read failed: HTTP 502"))
            code, out = self.cli(head, raising, env={CASE_BODY: body})
            self.assertIn(RUN_URL, raising.urls, "the cited run was never read, so the case proves nothing")
            self.assert_unread_line(code, out, "the read raises", "HTTP 502")

        with self.subTest("no run reader"), unittest.mock.patch.object(merge.Host, "__init__", no_host):
            code, out = self.cli(head, Runs(("success", head)), env={CASE_BODY: body})
            self.assert_unread_line(code, out, "no run reader", "merge cannot build the Host")

    def assert_unread_line(self, code, out, label, fact):
        lines = [ln for ln in out.splitlines() if ln.startswith("silent-undo: cite for ")]
        self.assertEqual(len(lines), 1, "%s: want one 'cite for' line, got %r:\n%s" % (label, lines, out))
        self.assertTrue(lines[0].startswith("silent-undo: cite for %s not accepted: " % self.SLUG), "%s: %s" % (label, lines[0]))
        self.assertNotIn(" not read: ", out, "%s: the old 'not read' line is still printed:\n%s" % (label, out))
        self.assertIn(fact, lines[0], "%s: the line does not give the reader's failure %r: %s" % (label, fact, lines[0]))
        self.assertEqual(code, 1, "%s: an unread cite must still fail the check:\n%s" % (label, out))

    def test_a_body_with_no_cite_prints_no_cite_line(self):  # control
        head, _ = self.cited_close()
        code, out = self.cli(head, Runs(("success", head)), env={CASE_BODY: "A summary with no cite.\n"})
        self.assertEqual([ln for ln in out.splitlines() if "silent-undo: cite for " in ln], [], out)
        self.assertEqual(code, 1, out)

    def clean_head(self):
        """A branch cut from main that adds one unrelated file, so it has no finding. -> its head sha."""
        self.r.sh("checkout", "-q", "-b", "clean")
        self.r.put("notes/unrelated.txt", "an unrelated note\n")
        self.r.sh("add", "-A")
        self.r.sh("commit", "-q", "-m", "add an unrelated note")
        return self.r.sh("rev-parse", "HEAD")

    def test_a_clean_branch_builds_no_run_reader_even_with_a_cite(self):
        import merge  # lazy, as in cli()
        head = self.clean_head()
        problems, _ = self.silent(head)
        self.assertEqual(problems, [], "premise: the branch has no finding, so a cite has nothing to excuse")
        built = []

        def record(host, *args, **kw):
            built.append((args, kw))

        runs = Runs(("success", head))
        with unittest.mock.patch.object(merge.Host, "__init__", record):
            code, out = self.cli(head, runs, env={CASE_BODY: self.CITE % (self.SLUG, RUN_URL)})
        self.assertEqual(built, [], "the merge tool's Host was built on a branch with no finding: the reader is built only for a finding")
        self.assertEqual(runs.urls, [], "the run reader was asked on a branch with no finding")
        self.assertEqual(code, 0, out)

    PASS_RETIRE = "Delete the old helper. Check: `tests/test_pass.py`."  # a runnable test: it passes on the head when it runs

    @staticmethod
    def judgment_raises(error):
        """Patch the debt-close judgment (check_debt_retire.judged) to raise `error`: the judgment cannot be read."""
        def raising(*a, **k):
            raise error
        return unittest.mock.patch.object(D, "judged", raising)

    def cited_edit(self):
        """A debt landed by a PR, then main adds NOTE_LINE after the cut; the branch takes that line out of the debt in place. The
        edit undoes main's line, so the debt has a finding and is edited, not deleted. -> (head, body)."""
        self.land({self.DEBT: debt(PROSE)})
        self.cut_then_main_adds_the_note()
        self.drop_note(self.DEBT)
        self.r.sh("add", "-A")
        self.r.sh("commit", "-q", "-m", "take main's line out of the debt")
        head = self.r.sh("rev-parse", "HEAD")
        names = self.r.sh("diff", "--name-status", "-M", "origin/main", head).splitlines()
        self.assertIn("M\t" + self.DEBT, names, "the PR does not edit the debt in place, so the case proves nothing")
        return head, self.CITE % (self.SLUG, RUN_URL)

    def test_a_cited_edit_prints_no_cite_line_when_the_judgment_cannot_be_read(self):  # F1: a modified debt is no delete
        head, body = self.cited_edit()
        bare, _ = self.silent(head)
        self.assertTrue(self.finding(bare, self.DEBT), "premise: the edit undoes main's line, so the debt has a finding with no cite")
        with self.judgment_raises(D.Unknown("the history read failed: boom")):
            problems, notes = self.silent(head, body, Runs(("success", head)))
        self.assertTrue(self.finding(problems, self.DEBT), (problems, notes))
        self.assert_no_cite_line(notes, "a modified debt, judgment unreadable")

    def test_a_cited_delete_prints_exactly_one_cite_line_when_the_judgment_cannot_be_read(self):  # F1: one line per deleted debt
        head, body = self.two_cited_closes()
        bare, _ = self.silent(head)
        self.assertTrue(self.finding(bare, self.DEBT), "premise: the delete undoes main's line, so the debt has a finding with no cite")
        with self.judgment_raises(D.Unknown("the history read failed: boom")):
            problems, notes = self.silent(head, body, Runs(("success", head)))
        self.assertTrue(self.finding(problems, self.DEBT), (problems, notes))
        self.assert_not_accepted(notes, "boom", "a deleted debt, judgment unreadable")

    def test_a_cited_delete_prints_no_cite_line_when_the_status_read_also_fails(self):  # F1: the status read fails too
        head, body = self.two_cited_closes()
        bare, _ = self.silent(head)
        self.assertTrue(self.finding(bare, self.DEBT), "premise: the delete undoes main's line, so the debt has a finding with no cite")

        def status_fails(*a, **k):
            raise D.Unknown("the status read failed: boom")
        with self.judgment_raises(D.Unknown("the history read failed: boom")), \
                unittest.mock.patch.object(D.records, "changes", status_fails):
            problems, notes = self.silent(head, body, Runs(("success", head)))
        self.assertTrue(self.finding(problems, self.DEBT), (problems, notes))
        self.assert_no_cite_line(notes, "judgment and status read both unreadable")

    def test_an_unrunnable_retire_with_a_failed_cited_run_gives_the_run_verdict_without_wrapping(self):  # F2
        head, body = self.two_cited_closes(retire=self.PASS_RETIRE)

        def cannot_run(wt, span, timeout):
            return "unknown", "%s did not start" % span
        with unittest.mock.patch.object(D, "run_span", cannot_run):
            self.assertIn((self.SLUG, "red"), self.scope(head, body, Runs(("failure", head))), "scope: the cited red run gives the flagged close its kind")
            problems, notes = self.silent(head, body, Runs(("failure", head)))
        self.assertTrue(self.finding(problems, self.DEBT), (problems, notes))
        want = "cite for %s not accepted: debt %s: the cited run %s ended failure, not success" % (self.SLUG, self.SLUG, RUN_URL)
        self.assertIn(want, notes, "the note does not give the run verdict as the debt-close check words it:\n%r" % (notes,))

    def test_a_judgment_that_raises_a_plain_error_names_its_type(self):  # F3
        head, body = self.two_cited_closes()
        with self.judgment_raises(KeyError("x")):
            problems, notes = self.silent(head, body, Runs(("success", head)))
        self.assertTrue(self.finding(problems, self.DEBT), (problems, notes))
        self.assert_not_accepted(notes, "KeyError", "a plain error")
        self.assertNotIn("the debt read failed", [n for n in notes if n.startswith("cite for ")][0], "the note names the read, not the type")


CHECKS_YML = os.path.join(HERE, "..", ".github", "workflows", "checks.yml")
ACTION_YML = os.path.join(HERE, "..", "actions", "silent-undo", "action.yml")
STEP = "Silent undo check"
INLINE_BODY = re.compile(r"\$\{\{(?:(?!\}\}).)*body", re.S)  # a body expression, across lines and past a `{0}`: a template injection in a run: line


def squash(value):
    """A map value with its whitespace removed, so `${{ x }}` and `${{x}}` read alike. None reads as empty."""
    return re.sub(r"\s+", "", value or "")


def action_steps(text):
    """action.yml's steps, re-indented to checks.yml's layout: the action's steps sit two spaces left of it, and the shared
    step parser (lint/workflow_steps.py) reads that layout."""
    return ["\n".join("  " + ln if ln.strip() else ln for ln in piece.split("\n"))
            for piece in re.split(r"^(?=    - )", text, flags=re.M)[1:]]


class CheckStepPins(unittest.TestCase):
    """The silent-undo check gets the PR body in its env var PR_BODY, and no run: line inlines it (zizmor's template injection).
    The checks job's step and the composite action's step both pass it. Steps are read through lint/workflow_steps.py."""

    def setUp(self):
        with open(CHECKS_YML, encoding="utf-8") as f:
            self.checks = f.read()
        with open(ACTION_YML, encoding="utf-8") as f:
            self.action = f.read()

    def checks_step(self):
        step = next((st for st in step_blocks(job_block(self.checks, "checks")) if step_key(st, "name") == STEP), None)
        self.assertIsNotNone(step, "the checks job has no step named %r" % STEP)
        return step

    def action_step(self):
        steps = action_steps(self.action)
        self.assertEqual(len(steps), 1, "action.yml has %d steps, want the one check" % len(steps))
        return steps[0]

    def assert_env(self, step, label):
        env = step_env(step)
        self.assertEqual(squash(env.get("PR_BODY")), squash("${{ github.event.pull_request.body }}"),
                         "%s: env PR_BODY is not the PR body" % label)
        self.assertEqual(squash(env.get("GH_TOKEN")), squash("${{ github.token }}"), "%s: env GH_TOKEN is not the workflow token" % label)

    def test_the_checks_step_passes_the_body_by_name(self):
        self.assertRegex(run_body(self.checks_step()) or "", r"--pr-body-env\s+PR_BODY\b",
                         "the checks step's run: does not pass --pr-body-env PR_BODY")

    def test_the_checks_step_maps_the_body_and_the_token_in_its_env(self):
        self.assert_env(self.checks_step(), "checks step")

    def test_the_action_step_maps_the_body_and_the_token_in_its_env(self):
        self.assert_env(self.action_step(), "action step")

    def test_no_run_line_in_either_file_inlines_the_pr_body(self):
        runs = [(step_key(st, "name") or "unnamed step", run_body(st)) for st in step_blocks(self.checks)]
        runs.append(("action.yml step", run_body(self.action_step())))
        read = [label for label, run in runs if run is not None]
        self.assertGreater(len(read), 50, "the scan read %d run: lines, so it covered nothing" % len(read))
        for label, run in runs:
            with self.subTest(step=label):
                self.assertIsNone(INLINE_BODY.search(run or ""), "%s inlines the PR body in its run: line" % label)

    def test_the_scan_flags_an_inline_body_in_a_run(self):  # control: the pattern is not vacuous
        self.assertIsNotNone(INLINE_BODY.search('echo "${{ github.event.pull_request.body }}"'))
        self.assertIsNotNone(INLINE_BODY.search("echo \"${{ format('{0}', github.event.pull_request.body) }}\""), "a format() wrapper hides the body")
        self.assertIsNotNone(INLINE_BODY.search("echo \"${{ format('{0}',\n  github.event.pull_request.body) }}\""), "a multi-line expression hides the body")
        self.assertIsNone(INLINE_BODY.search('echo "${{ env.PR_BODY }}"'))


NO_BASE = {"GITHUB_BASE_REF": None}  # a PR run sets GITHUB_BASE_REF; the no-base reads pop it (None pops a name)
STACK_BASE = "line 1\nadded by pr-base\n" + "".join("line %d\n" % i for i in range(2, 21)) + "function Card() {}\n"
NO_LINE_1 = "".join("line %d\n" % i for i in range(2, 21)) + "function Card() {}\n"
MAIN_WITHOUT_LINE_1 = "added by pr-base\n" + "".join("line %d\n" % i for i in range(2, 21)) + "function Card() {}\n"
EMPTY_BASE = re.compile(r"origin/(?![\w.-])")  # a note naming origin/ with no branch name: an empty base read as a candidate


class PrBase(unittest.TestCase):
    """Which base a local run reads a branch against when it names none: the PR's base, else origin/main.

    The shared fixture is a lane off `pr-base`, which adds a line after `line 1`. Main deletes `line 1`, and the lane
    merges main with `-X <strategy>`: `theirs` drops pr-base's added line, `ours` puts `line 1` back. Each case first
    reads the explicit bases with check(), so only the default choice is under test."""

    def setUp(self):
        self.r = base_repo()

    def stack(self, strategy, base_text=STACK_BASE, main_text=NO_LINE_1):
        r = self.r
        r.sh("checkout", "-q", "-b", "pr-base")
        r.commit("pr-base adds a line", app_txt=base_text)
        r.sh("push", "-q", "origin", "pr-base")
        r.sh("checkout", "-q", "-b", "lane", "pr-base")
        r.commit("lane edits other", other_txt="other v2\n")
        r.sh("checkout", "-q", "main")
        r.commit("main deletes line 1", app_txt=main_text)
        r.push()
        r.sh("checkout", "-q", "lane")
        r.sh("merge", "-q", "--no-edit", "-X", strategy, "origin/main")

    def explicit(self, upstream):
        """check() against an explicit base: the verdict the default run must match."""
        return C.check(self.r.dir, upstream, "HEAD")[0]

    def run_main(self, argv, env=None):
        return PrintedFindings.run_main(self, argv, "utf-8", env)

    def run_default(self, env=None):
        """main() with no --upstream: the run under test. No-base env unless the case names a base."""
        return self.run_main(["--repo", self.r.dir], env={**NO_BASE, **(env or {})})

    def assert_theirs_scope(self):
        """Scope first: origin/main is quiet on the theirs lane, and origin/pr-base names the dropped base line."""
        self.assertEqual(self.explicit("origin/main"), [], "scope: origin/main should be quiet on this lane")
        base_bad = self.explicit("origin/pr-base")
        self.assertTrue(any("added by pr-base" in p for p in base_bad), "scope: origin/pr-base should name the dropped line: %r" % base_bad)

    def revert_of_main_line(self, how):
        """pr-base adds a line after `line 1`, and main takes it in: how="merge" by a true merge commit, how="squash"
        by one commit with the same change. Main then deletes `line 1`, and a lane branched from main reverts that
        deletion. The lane's gh-merge-base names pr-base."""
        r = self.r
        r.sh("checkout", "-q", "-b", "pr-base")
        r.commit("pr-base adds a line", app_txt=STACK_BASE)
        r.sh("push", "-q", "origin", "pr-base")
        r.sh("checkout", "-q", "main")
        if how == "merge":
            r.sh("merge", "-q", "--no-ff", "--no-edit", "pr-base")
        else:
            r.sh("merge", "-q", "--squash", "pr-base")
            r.sh("commit", "-q", "-m", "squash pr-base")
        r.commit("main deletes line 1", app_txt=MAIN_WITHOUT_LINE_1)
        r.push()
        r.sh("checkout", "-q", "-b", "lane")
        r.sh("revert", "--no-edit", "HEAD")
        r.sh("config", "branch.lane.gh-merge-base", "pr-base")

    def test_merged_base_is_passed_over_and_the_run_fails_as_main_does(self):
        self.revert_of_main_line("merge")
        self.r.sh("merge-base", "--is-ancestor", "origin/pr-base", "origin/main")  # scope: pr-base is merged into main
        main_fails = ["silent-undo: FAIL: " + p for p in self.explicit("origin/main")]
        self.assertTrue(main_fails, "scope: origin/main should FAIL on the revert of main's deletion")
        rc, text = self.run_default()
        fails = [x for x in text.splitlines() if x.startswith("silent-undo: FAIL: ")]
        self.assertEqual(fails, main_fails, "the default run read the merged base and printed no FAIL for the revert of main's line")
        self.assertIn("origin/pr-base", text, "no note says the merged base origin/pr-base was passed over")
        self.assertEqual(rc, 1, "the default run exited %d, not 1" % rc)

    def test_squashed_base_is_named_in_the_run_output(self):
        self.revert_of_main_line("squash")
        self.assertIn("added by pr-base", self.r.sh("show", "origin/main:app.txt"), "scope: main should hold the squashed line")
        rc, text = self.run_default()
        self.assertTrue([x for x in text.splitlines() if "origin/pr-base" in x], "the run read the squashed base origin/pr-base and its output names no base: a silent pass")

    def test_resolved_base_prints_a_note_naming_it_and_its_source(self):
        self.stack("ours")
        self.r.sh("config", "branch.lane.gh-merge-base", "pr-base")
        self.r.sh("merge-base", "--is-ancestor", "origin/pr-base", "HEAD")  # scope: pr-base is the lane's base
        rc, text = self.run_default()
        notes = [x for x in text.splitlines() if "origin/pr-base" in x and "gh-merge-base" in x]
        self.assertTrue(notes, "the run read origin/pr-base from gh-merge-base and printed no note naming it and its source: %r" % text)

    def test_config_names_the_base_and_the_dropped_base_line_is_read_against_it(self):
        self.stack("theirs")
        self.r.sh("config", "branch.lane.gh-merge-base", "pr-base")
        self.assert_theirs_scope()
        rc, text = self.run_default()
        self.assertIn("added by pr-base", text, "the default run is quiet on a lane that drops its base's line: it read against origin/main")
        self.assertEqual(rc, 1, "the default run printed the dropped line but did not exit 1")

    def test_env_names_the_base_and_the_dropped_base_line_is_read_against_it(self):
        self.stack("theirs")
        self.assert_theirs_scope()
        rc, text = self.run_default({"GITHUB_BASE_REF": "pr-base"})
        self.assertIn("added by pr-base", text, "the default run is quiet on a lane that drops its base's line: GITHUB_BASE_REF=pr-base was not read")
        self.assertEqual(rc, 1, "the default run printed the dropped line but did not exit 1")

    def test_candidate_base_that_holds_the_head_is_rejected_and_named(self):
        self.stack("ours")
        r = self.r
        r.sh("push", "-q", "origin", "lane")
        r.sh("fetch", "-q", "origin")
        r.sh("config", "branch.lane.gh-merge-base", "lane")
        r.sh("merge-base", "--is-ancestor", "HEAD", "origin/lane")  # scope: origin/lane already holds the head
        self.assertTrue(self.explicit("origin/main"), "scope: origin/main should FAIL on this lane")
        rc, text = self.run_default()
        self.assertIn("undoing", text, "the FAIL against origin/main did not print: a rejected candidate silenced the run")
        self.assertIn("origin/lane", text, "the run printed no note naming the rejected candidate origin/lane")
        self.assertEqual(rc, 1, "the run printed the FAIL but did not exit 1")

    def test_no_base_found_names_origin_main_and_says_the_base_is_unknown(self):
        self.r.sh("checkout", "-q", "-b", "lane")
        self.r.commit("lane edits other", other_txt="other v2\n")
        rc, text = self.run_default()
        notes = [line for line in text.splitlines() if "origin/main" in line and "unknown" in line.lower()]
        self.assertTrue(notes, "no line names origin/main as the base and says the PR base is unknown: %r" % text)
        self.assertEqual(rc, 0, "a clean lane with no base named exited %d" % rc)

    def test_missing_origin_main_falls_back_to_local_main_with_a_note(self):
        self.r.sh("checkout", "-q", "-b", "lane")
        self.r.commit("lane edits other", other_txt="other v2\n")
        self.r.sh("update-ref", "-d", "refs/remotes/origin/main")
        rc, text = self.run_default()
        self.assertIn("no origin/main here, compared against the local main", text, "the run fell back to local main with no note saying so")
        self.assertEqual(rc, 0, "a clean lane on local main exited %d" % rc)

    def test_clean_stack_stays_quiet_against_its_base(self):  # control: a merge with no conflict is quiet on either base
        clean_base = "".join("line %d\n" % i for i in range(1, 21)) + "added by pr-base\nfunction Card() {}\n"
        clean_main = "line 1\n" + "".join("line %d\n" % i for i in range(3, 21)) + "function Card() {}\n"
        self.stack("theirs", base_text=clean_base, main_text=clean_main)
        self.r.sh("config", "branch.lane.gh-merge-base", "pr-base")
        self.assertEqual(self.explicit("origin/main"), [], "scope: origin/main should be quiet on the clean stack")
        self.assertEqual(self.explicit("origin/pr-base"), [], "scope: origin/pr-base should be quiet on the clean stack")
        rc, text = self.run_default()
        self.assertEqual(rc, 0, "a clean stack read against its base exited %d: %r" % (rc, text))

    def test_explicit_upstream_keeps_its_verdict_and_prints_no_base_note(self):  # control
        self.stack("ours")
        self.r.sh("config", "branch.lane.gh-merge-base", "pr-base")
        expected = ["silent-undo: FAIL: " + p for p in self.explicit("origin/main")]
        self.assertTrue(expected, "scope: origin/main should FAIL on this lane")
        rc, text = self.run_main(["--repo", self.r.dir, "--upstream", "origin/main"], env=NO_BASE)
        lines = text.splitlines()
        self.assertEqual([x for x in lines if x.startswith("silent-undo: FAIL: ")], expected, "an explicit --upstream changed its FAIL lines")
        extra = [x for x in lines if not x.startswith("silent-undo: FAIL: ") and not x.startswith("silent-undo: put the work back")]
        self.assertEqual(extra, [], "an explicit --upstream printed a line it did not print before")
        self.assertEqual(rc, 1)

    def test_lane_on_main_keeps_its_verdict_with_no_base_named(self):  # control
        self.r.commit("main deletes line 1", app_txt=NO_LINE_1)
        self.r.push()
        self.r.sh("checkout", "-q", "-b", "oops")
        self.r.sh("revert", "--no-edit", "HEAD")
        expected = ["silent-undo: FAIL: " + p for p in self.explicit("origin/main")]
        self.assertTrue(expected, "scope: origin/main should FAIL on the revert")
        rc, text = self.run_default()
        self.assertEqual([x for x in text.splitlines() if x.startswith("silent-undo: FAIL: ")], expected, "the default run's FAIL lines changed on a lane off main")
        self.assertEqual(rc, 1)

    def test_merge_that_restores_a_line_main_deleted_is_read_against_the_base_only_with_the_base_set(self):  # control
        self.stack("ours")
        self.r.sh("config", "branch.lane.gh-merge-base", "pr-base")
        self.r.sh("merge-base", "--is-ancestor", "origin/pr-base", "HEAD")  # scope: pr-base is the lane's base
        self.assertTrue(any("main deletes line 1" in p for p in self.explicit("origin/main")), "scope: origin/main should FAIL on the restored line")
        base_fails = ["silent-undo: FAIL: " + p for p in self.explicit("origin/pr-base")]
        rc, text = self.run_default()
        fails = [x for x in text.splitlines() if x.startswith("silent-undo: FAIL: ")]
        self.assertEqual(fails, base_fails, "the default run with the base set printed FAIL lines other than the base's own run")
        self.assertNotIn("main deletes line 1", text, "the default run with the base set read the lane against origin/main")
        self.assertEqual(rc, 0, "the default run with the base set exited %d on a lane the base holds" % rc)
        rc, text = self.run_main(["--repo", self.r.dir, "--upstream", "origin/main"], env=NO_BASE)
        self.assertIn("main deletes line 1", text, "an explicit --upstream origin/main lost the FAIL for the restored line")
        self.assertEqual(rc, 1, "an explicit --upstream origin/main exited %d, not 1" % rc)

    def test_empty_github_base_ref_is_unset(self):
        self.stack("theirs")
        self.r.sh("config", "branch.lane.gh-merge-base", "pr-base")
        self.assert_theirs_scope()
        rc, text = self.run_default({"GITHUB_BASE_REF": ""})
        self.assertIsNone(EMPTY_BASE.search(text), "GITHUB_BASE_REF='' was read as a candidate: a note names origin/ with no branch: %r" % text)
        source = [x for x in text.splitlines() if "origin/pr-base" in x and "gh-merge-base" in x]
        self.assertTrue(source, "the note does not name origin/pr-base and the gh-merge-base source: %r" % text)
        self.assertIn("added by pr-base", text, "GITHUB_BASE_REF='' was not read as unset: the configured pr-base was not used")
        self.assertEqual(rc, 1, "the run printed the base's FAIL but exited %d, not 1" % rc)
        self.r.sh("config", "--unset", "branch.lane.gh-merge-base")
        rc, text = self.run_default({"GITHUB_BASE_REF": ""})
        self.assertIsNone(EMPTY_BASE.search(text), "with no base named, a note names origin/ with no branch: %r" % text)
        notes = [x for x in text.splitlines() if "origin/main" in x and "unknown" in x.lower()]
        self.assertTrue(notes, "with no base named, no line says the base is unknown and names origin/main: %r" % text)
        self.assertEqual(rc, 0, "the default run on origin/main exited %d on a lane origin/main holds" % rc)

    def test_base_named_main_is_read_as_the_base_not_passed_over_as_merged(self):
        self.r.sh("checkout", "-q", "-b", "lane")
        self.r.commit("lane edits other", other_txt="other v2\n")
        self.r.sh("config", "branch.lane.gh-merge-base", "main")
        rc, text = self.run_default()
        self.assertIn("compared against the PR base origin/main", text, "a base named main was not read as the PR base: no note says so: %r" % text)
        self.assertNotIn("unknown", text.lower(), "a base named main fell through to the unknown-base note: %r" % text)
        self.assertNotIn("already merged", text, "a base named main was passed over as merged into main: %r" % text)
        self.assertEqual(rc, 0, "a clean lane read against a base named main exited %d" % rc)


def card(*added):
    """app.txt as base_repo() writes it, with each of `added` after the Card function."""
    return BODY + "function Card() {}\n" + "".join(line + "\n" for line in added)


class MergedMain(unittest.TestCase):
    """Main's own commits, read on a branch that merged main in. A merge that main made, and a change that main
    took out, are main's work, not the branch's, so a local run of the branch against its base must not flag them.
    Each case runs main() with an explicit --upstream, so the verdict under test is the one the base names."""

    def setUp(self):
        self.r = base_repo()

    def run_main(self, upstream):
        argv = ["--repo", self.r.dir, "--upstream", upstream, "--head", "HEAD", "--strict"]
        return PrintedFindings.run_main(self, argv, "utf-8")

    def listed(self, rev, sha):
        return sha in self.r.sh("rev-list", rev).split()

    def cut_base(self, msg, **files):
        """Branch B is cut off main with one commit of its own, and pushed. Back on main. -> that commit."""
        r = self.r
        r.sh("checkout", "-q", "-b", "B")
        sha = r.commit(msg, **files)
        r.sh("push", "-q", "origin", "B")
        r.sh("checkout", "-q", "main")
        return sha

    def lane_from_base(self):
        self.r.sh("checkout", "-q", "-b", "lane", "origin/B")

    def main_drops_a_feature_line(self):
        """Main merges a feature and takes its added line out by hand. A lane off B then merges main. -> main's merge."""
        r = self.r
        self.cut_base("B edits other", other_txt="other v1.5\n")
        r.sh("checkout", "-q", "-b", "feat")
        r.commit("feat adds a line", app_txt=card("feature line"))
        r.sh("checkout", "-q", "main")
        r.sh("merge", "-q", "--no-commit", "--no-ff", "feat")
        merge = r.commit("Merge feat, drop its line", app_txt=card())
        r.push()
        self.lane_from_base()
        r.commit("lane edits other", other_txt="other v2\n")
        r.sh("merge", "-q", "--no-edit", "origin/main")
        return merge

    def test_a_main_merge_that_drops_its_feature_line_is_not_read_on_a_branch_that_merged_main(self):
        r = self.r
        merge = self.main_drops_a_feature_line()
        self.assertTrue(self.listed("origin/main", merge), "scope: main's merge is not on origin/main")
        self.assertFalse(self.listed("origin/B", merge), "scope: origin/B already holds main's merge")
        self.assertIn(merge, r.sh("rev-list", "--merges", "origin/B..HEAD").split(), "scope: the lane's range does not reach main's merge")
        rc, out = self.run_main("origin/B")
        self.assertEqual(rc, 0, out)

    def test_a_main_change_that_takes_out_a_line_the_base_tip_added_is_not_read_on_a_branch_that_merged_main(self):
        r = self.r
        tip = self.cut_base("B adds a branch line", app_txt=card("branch line"))
        r.commit("main adds the same line", app_txt=card("branch line"))
        r.push()
        self.lane_from_base()
        r.sh("merge", "-q", "--no-edit", "origin/main")  # the lane takes main's line in before main takes it out
        r.sh("checkout", "-q", "main")
        takes_out = r.commit("main takes its line out", app_txt=card())
        r.push()
        r.sh("checkout", "-q", "lane")
        r.sh("merge", "-q", "--no-edit", "origin/main")
        self.assertEqual(r.sh("rev-parse", "origin/B"), tip, "scope: origin/B is not at the base tip")
        self.assertTrue(self.listed("origin/main", takes_out), "scope: the change that takes the line out is not on origin/main")
        self.assertFalse(self.listed("origin/B", takes_out), "scope: origin/B already holds the change that takes the line out")
        rc, out = self.run_main("origin/B")
        self.assertEqual(rc, 0, out)

    def test_a_lane_merge_that_drops_a_line_main_added_still_fails(self):  # control
        r = self.r
        self.cut_base("B adds a branch line", app_txt=card("branch line"))
        r.commit("main adds a line to other", other_txt="other v1\nmain line\n")
        r.push()
        self.lane_from_base()
        r.sh("merge", "-q", "--no-commit", "--no-ff", "origin/main")
        r.commit("Merge main, drop its line", other_txt="other v1\n")
        self.assertIn("main line", r.sh("show", "origin/main:other.txt"), "scope: main does not hold the line the lane drops")
        rc, out = self.run_main("origin/B")
        self.assertEqual(rc, 1, out)
        self.assertIn("- main line", out)

    def test_a_lane_commit_that_takes_out_a_line_the_base_tip_added_still_fails(self):  # control
        self.cut_base("B adds a branch line", app_txt=card("branch line"))
        self.lane_from_base()
        self.r.commit("lane takes its line out", app_txt=card())
        rc, out = self.run_main("origin/B")
        self.assertEqual(rc, 1, out)
        self.assertIn("undoing", out)

    def test_explicit_origin_main_is_unchanged_on_a_lane_that_merged_main(self):  # control
        self.main_drops_a_feature_line()
        rc, out = self.run_main("origin/main")
        self.assertEqual(rc, 0, out)

    def test_a_lane_that_takes_out_a_base_line_still_fails_when_main_touched_the_file(self):  # control: the file filter reads a lane edit
        r = self.r
        self.cut_base("B adds a base line", app_txt=card("base line"))
        fork = r.sh("rev-parse", "origin/main")
        r.commit("main edits the top line", app_txt=BODY.replace("line 1\n", "main top\n", 1) + "function Card() {}\n")
        r.push()
        self.lane_from_base()
        r.sh("merge", "-q", "--no-edit", "origin/main")
        r.commit("lane takes its base line out and edits line 2",
                 app_txt=BODY.replace("line 1\n", "main top\n", 1).replace("line 2\n", "lane two\n", 1) + "function Card() {}\n")
        self.assertIn("app.txt", r.sh("diff", "--name-only", fork, "origin/main").split(), "scope: main did not touch app.txt")
        self.assertNotEqual(r.sh("show", "HEAD:app.txt"), r.sh("show", "origin/main:app.txt"),
                            "scope: the lane's app.txt equals main's, so the file filter would read nothing")
        rc, out = self.run_main("origin/B")
        self.assertEqual(rc, 1, out)
        self.assertIn("undoing", out)

    def test_an_unpushed_main_merge_is_read_when_the_upstream_is_origin_main(self):
        r = self.r
        self.assertEqual(r.sh("rev-parse", "--verify", "-q", "origin/HEAD", ok=False), "",
                         "scope: origin/HEAD is set, so the default is not the local main")
        r.sh("checkout", "-q", "-b", "feat")
        r.commit("feat adds a line", app_txt=card("feature line"))
        r.sh("checkout", "-q", "main")
        r.sh("merge", "-q", "--no-commit", "--no-ff", "feat")
        merge = r.commit("Merge feat, drop its line", app_txt=card())  # local main only: never pushed
        self.assertFalse(self.listed("origin/main", merge), "scope: the merge is already on origin/main")
        self.assertTrue(self.listed("main", merge), "scope: the merge is not on local main")
        r.sh("checkout", "-q", "-b", "lane", "origin/main")
        r.commit("lane edits other", other_txt="other v2\n")
        r.sh("merge", "-q", "--no-edit", "main")
        self.assertIn(merge, r.sh("rev-list", "--merges", "origin/main..HEAD").split(), "scope: the lane's range does not reach the unpushed merge")
        rc, out = self.run_main("origin/main")
        self.assertEqual(rc, 1, out)
        self.assertIn("feature line", out)


if __name__ == "__main__":
    unittest.main()
