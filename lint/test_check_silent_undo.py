#!/usr/bin/env python3
"""Fixture suite for lint/check_silent_undo.py. Run: python3 lint/test_check_silent_undo.py

Every case builds a throwaway repo with a local `origin` and asks the check for a verdict.
Red cases: a squash that carries the pre-deletion copy of a file (a revert nobody wrote), and a
merge that drops a parent's added line.
"""
import contextlib, io, json, os, shutil, subprocess, sys, tempfile, unittest, unittest.mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "merge"))
import check_silent_undo as C  # noqa: E402
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import tracked_tree  # noqa: E402  copies what git lists, so no fixture lists files (testing/tracked_tree.py)

ENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull, GIT_AUTHOR_NAME="t",
           GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
os.environ.update({k: ENV[k] for k in ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL")})

BODY = "".join("line %d\n" % i for i in range(1, 21))


REPOS = []


def tearDownModule():
    for r in REPOS:
        r.tmp.cleanup()


class Repo:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        REPOS.append(self)
        self.dir = os.path.join(self.tmp.name, "w")
        origin = os.path.join(self.tmp.name, "o.git")
        self.sh("init", "-q", "--bare", origin, cwd=self.tmp.name)
        self.sh("init", "-q", "-b", "main", self.dir, cwd=self.tmp.name)
        self.sh("remote", "add", "origin", origin)

    def sh(self, *a, cwd=None, ok=True, date=None):
        env = dict(os.environ, GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date) if date else None
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

    def merged_pr(self, branch="pr1"):
        """PR 1: deletes Card from app.txt, merges into main with a merge commit."""
        r = self.r
        r.sh("checkout", "-q", "-b", branch)
        r.commit("delete Card", app_txt=BODY)
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
    """Lines that look alike but claim something else must not pass as a rewrite."""
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

    def run_main(self, argv, encoding):
        """main(argv) with stdout a strict stream of `encoding`. -> (rc, what was printed). A raise is a failure."""
        out = io.TextIOWrapper(io.BytesIO(), encoding=encoding, errors="strict", newline="\n")
        with unittest.mock.patch.dict(os.environ), contextlib.redirect_stdout(out):
            os.environ.pop("CI", None)
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
        for k, v in (("gpg.format", "ssh"), ("user.signingkey", key), ("gpg.ssh.allowedSignersFile", signers),
                     ("commit.gpgsign", "true"), ("log.showSignature", "true")):
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


if __name__ == "__main__":
    unittest.main()
