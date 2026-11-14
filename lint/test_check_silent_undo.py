#!/usr/bin/env python3
"""Fixture suite for lint/check_silent_undo.py. Run: python3 lint/test_check_silent_undo.py

Every case builds a throwaway repo with a local `origin` and asks the check for a verdict.
Red cases: a squash that carries the pre-deletion copy of a file (a revert nobody wrote), and a
merge that drops a parent's added line.
"""
import atexit, contextlib, inspect, io, json, os, shutil, subprocess, sys, tempfile, unittest, unittest.mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: the run folder's one home (lint/_test_temp.py)
import check_debt_retire as D  # noqa: E402  the debt-close check: the scope each Retire-run case is read against
from test_check_debt_retire import PROSE, RUN_URL, Runs, debt  # noqa: E402  one home of the debt shape and the fake run reader
sys.path.insert(0, os.path.join(HERE, "..", "merge"))
import check_silent_undo as C  # noqa: E402
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

    # Claude's session URL line follows the attribution: as its own paragraph, or on the attribution's next line. The URL is
    # no prose, so the key line above the attribution still counts, as it does without the URL.
    SESSION = "https://claude.ai/code/session_013NEJL2SdAA1CCG5eTFVFVr"

    def assert_reads_as_without_url(self, pairs):
        """Each (body without the URL, the same body with it): the first is excused (scope), and the second must be too."""
        for plain, with_url in pairs:
            with self.subTest(body=with_url):
                ok, why = self.excused(plain)
                self.assertTrue(ok, "scope: the body without the URL is not excused: %r" % (why,))
                ok, why = self.excused(with_url)
                self.assertTrue(ok, "a session URL line after the attribution hid the Drops-lines line: %r" % (why,))

    def test_a_session_url_after_the_attribution_reads_as_no_url(self):
        L, A, S, F = self.LINE, self.ATTR, self.SESSION, self.FOOT
        self.assert_reads_as_without_url([
            ("Summary.\n\n%s\n\n%s\n" % (L, A), "Summary.\n\n%s\n\n%s\n\n%s\n" % (L, A, S)),  # its own paragraph
            ("Summary.\n\n%s\n\n%s\n" % (L, A), "Summary.\n\n%s\n\n%s\n%s\n" % (L, A, S)),  # the attribution's next line
            ("Summary.\n\n%s\n\n%s\n" % (L, A), "Summary.\n\n%s\n\n%s\n\n  %s  \n\n\n" % (L, A, S)),  # padded, as the attribution case is
            ("Summary.\n\n%s\n\n%s\n\n---\n%s\n" % (L, A, F), "Summary.\n\n%s\n\n%s\n\n%s\n\n---\n%s\n" % (L, A, S, F)),  # footer after it
            ("Summary.\n\n%s\n\n%s\n\n---\n%s\n" % (L, A, F), "Summary.\n\n%s\n\n%s\n%s\n\n---\n%s\n" % (L, A, S, F)),  # next line, then footer
            ("%s\n\n%s\n" % (L, A), "%s\n\n%s\n\n%s\n" % (L, A, S)),  # no Summary: the key line is the only paragraph left
        ])

    def test_a_session_url_after_the_attribution_reads_as_no_url_with_crlf(self):
        L, A, S = self.LINE, self.ATTR, self.SESSION
        self.assert_reads_as_without_url([
            ("Summary.\r\n\r\n%s\r\n\r\n%s\r\n" % (L, A), "Summary.\r\n\r\n%s\r\n\r\n%s\r\n\r\n%s\r\n" % (L, A, S)),
            ("Summary.\r\n\r\n%s\r\n\r\n%s\r\n" % (L, A), "Summary.\r\n\r\n%s\r\n\r\n%s\r\n%s\r\n" % (L, A, S)),
        ])

    # The key line can share its paragraph with the attribution, with the session URL as its own paragraph after it. The
    # URL must not change the reading: the body without it is excused, so the body with it is too.
    def test_a_session_url_paragraph_after_a_key_line_in_the_attribution_paragraph_reads_as_no_url(self):
        L, S = self.LINE, self.SESSION
        bare = self.ATTR.split(" ", 1)[1]  # the attribution without the emoji, as the reviewer's body wrote it
        self.assert_reads_as_without_url([
            ("Summary.\n\n%s\n%s\n" % (L, bare), "Summary.\n\n%s\n%s\n\n%s\n" % (L, bare, S)),
            ("Summary.\n\n%s\n%s\n" % (L, self.ATTR), "Summary.\n\n%s\n%s\n\n%s\n" % (L, self.ATTR, S)),  # with the emoji
        ])

    def test_a_session_url_paragraph_after_a_key_line_in_the_attribution_paragraph_reads_as_no_url_with_crlf(self):
        L, S = self.LINE, self.SESSION
        bare = self.ATTR.split(" ", 1)[1]
        self.assert_reads_as_without_url([
            ("Summary.\r\n\r\n%s\r\n%s\r\n" % (L, bare), "Summary.\r\n\r\n%s\r\n%s\r\n\r\n%s\r\n" % (L, bare, S)),
            ("Summary.\r\n\r\n%s\r\n%s\r\n" % (L, self.ATTR), "Summary.\r\n\r\n%s\r\n%s\r\n\r\n%s\r\n" % (L, self.ATTR, S)),
        ])

    def test_a_session_url_paragraph_after_a_key_line_in_the_attribution_paragraph_and_prose_excuses_nothing(self):  # control
        L, S = self.LINE, self.SESSION
        bare = self.ATTR.split(" ", 1)[1]
        ok, why = self.excused("Summary.\n\n%s\n%s\n" % (L, bare))  # scope: the key line and attribution are read
        self.assertTrue(ok, "scope: the body without the URL is not excused: %r" % (why,))
        self.assert_nothing_excused(["Summary.\n\n%s\n%s\n\n%s\n\nClosing prose.\n" % (L, bare, S),
                                     "Summary.\n\n%s\n%s\n\n%s\nClosing prose.\n" % (L, bare, S)])  # prose on the URL's next line

    def test_a_session_url_paragraph_with_no_attribution_at_the_end_of_the_paragraph_above_is_prose(self):  # control
        L, S = self.LINE, self.SESSION
        bare = self.ATTR.split(" ", 1)[1]
        ok, why = self.excused("Summary.\n\n%s\n%s\n" % (L, bare))  # scope: the key line and attribution are read
        self.assertTrue(ok, "scope: the body without the URL is not excused: %r" % (why,))
        self.assert_nothing_excused(["Summary.\n\n%s\n\n%s\n" % (L, S),  # the key line alone, then the URL paragraph
                                     "Summary.\n\n%s\nSome other line\n\n%s\n" % (L, S),  # the paragraph above ends in other text
                                     "Summary.\n\n%s\n%s extra\n\n%s\n" % (L, bare, S),  # the attribution line has text after it
                                     "Summary.\n\n%s\n%s\nSome prose.\n\n%s\n" % (L, bare, S)])  # the paragraph above ends in prose

    def test_a_session_url_with_no_key_line_excuses_nothing(self):  # control
        L, A, S, F = self.LINE, self.ATTR, self.SESSION, self.FOOT
        ok, why = self.excused("Summary.\n\n%s\n\n%s\n" % (L, A))  # scope: the key line and attribution are read
        self.assertTrue(ok, "scope: the body with the key line and no URL is not excused: %r" % (why,))
        self.assert_nothing_excused(["Summary.\n\n%s\n\n%s\n" % (A, S),
                                     "Summary.\n\n%s\n%s\n" % (A, S),
                                     "Summary.\n\nSome prose.\n\n%s\n\n%s\n" % (A, S),
                                     "Summary.\n\n```\n%s\n```\n\n%s\n\n%s\n" % (L, A, S),  # a fenced key line is no key line
                                     "Summary.\n\n%s\n\n%s\n\n---\n%s\n" % (A, S, F)])

    def test_a_session_url_after_the_key_line_and_attribution_excuses_nothing_when_prose_follows(self):  # control
        L, A, S = self.LINE, self.ATTR, self.SESSION
        ok, why = self.excused("Summary.\n\n%s\n\n%s\n" % (L, A))  # scope: the key line and attribution are read
        self.assertTrue(ok, "scope: the body without the URL is not excused: %r" % (why,))
        self.assert_nothing_excused(["Summary.\n\n%s\n\n%s\n\n%s\n\nClosing prose.\n" % (L, A, S),
                                     "Summary.\n\n%s\n\n%s\n%s\nClosing prose.\n" % (L, A, S),
                                     "Summary.\n\n%s\n\n%s\nClosing prose.\n" % (L, A),  # prose on the attribution's next line
                                     "Summary.\n\n%s\n\nSome prose.\n\n%s\n\n%s\n" % (L, A, S)])  # prose between the key line and it

    def test_a_text_after_the_attribution_that_is_not_a_session_url_is_prose(self):  # control
        L, A, S = self.LINE, self.ATTR, self.SESSION
        ok, why = self.excused("Summary.\n\n%s\n\n%s\n" % (L, A))  # scope: the key line and attribution are read
        self.assertTrue(ok, "scope: the body without the URL is not excused: %r" % (why,))
        self.assert_nothing_excused(["Summary.\n\n%s\n\n%s\n\nhttps://example.com/code/session_013NEJL2SdAA1CCG5eTFVFVr\n" % (L, A),  # another host
                                     "Summary.\n\n%s\n\n%s\n\nhttps://claude.ai/code/notes\n" % (L, A),  # this host, no session
                                     "Summary.\n\n%s\n\n%s\n\nSee %s\n" % (L, A, S),  # text before the session URL
                                     "Summary.\n\n%s\n\n%s\n\n%s extra\n" % (L, A, S),  # text after it
                                     "Summary.\n\n%s\n\n%s\nhttps://example.com/\n" % (L, A)])  # the attribution's next line

    def test_a_key_line_in_the_attribution_paragraph_with_the_url_still_excuses(self):  # control, current behaviour
        L, A, S = self.LINE, self.ATTR, self.SESSION
        ok, why = self.excused("Summary.\n\n%s\n%s\n%s\n" % (L, A, S))
        self.assertTrue(ok, "a key line in the attribution's paragraph with the URL stopped excusing: %r" % (why,))


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

    def test_an_appended_negation_clause_keeps_the_rewrite_excuse(self):
        """A merge that only appends a clause with a negation word to main's rule line is no reversal: every original
        token survives in order. The line's final `.` moves after the clause, so the clause sits after the last word."""
        for result in ("Keep CI waits short, never past 55 minutes.", "Keep CI waits short; don't retry twice.",
                       "Keep CI waits short, without a second push."):
            with self.subTest(result=result):
                self.assertNotIn("Keep CI waits short.", result)  # the line is lost, never a substring of the merge
                self.assertEqual(self.resolve("", "Keep CI waits short.", result), [])

    def test_an_appended_clause_without_a_negation_passes(self):
        """The control for the appended cases: the same clause with no negation word passes on old code too, so the
        flag on the negated clause comes from the negation word, not the number or the comma."""
        result = "Keep CI waits short, under 55 minutes."
        self.assertNotIn("Keep CI waits short.", result)  # the line is lost, never a substring of the merge
        self.assertEqual(self.resolve("", "Keep CI waits short.", result), [])

    def test_a_negation_inserted_among_the_tokens_stays_a_reversal(self):
        """A negation word before the last word of a line is a reversal, never an appended clause. The first case is
        the true reversal the appended rule must not let through. Each case keeps its first token and every original
        token in order, so `extends` is the gate that flags it."""
        for a_line, result in (("Keep CI waits short.", "Keep CI waits not short."),
                               ("Claude can merge", "Claude can't merge"),
                               ("must pass", "must not pass")):
            with self.subTest(result=result):
                self.red("", a_line, result)


class MainLineDrop:
    """The one home of the fixture for a case that merges main into a feat branch and drops lines main added to
    app.txt. main is pushed with app.txt at BODY, and feat is cut from it with the commit `cut_feat` writes."""
    T0, T1, T2 = "2026-01-01T10:00:00", "2026-01-02T10:00:00", "2026-01-03T10:00:00"

    def cut_feat(self, msg, **files):
        r = self.r = Repo()
        r.put("app.txt", BODY)
        r.commit("base", date="2025-12-01T10:00:00", other_txt="o1\n")
        r.push()
        r.sh("checkout", "-q", "-b", "feat")
        r.commit(msg, date=self.T0, **files)

    def main_commit(self, msg, date, **files):
        """A commit on main, pushed; the checkout goes back to feat."""
        r = self.r
        r.sh("checkout", "-q", "main")
        r.commit(msg, date=date, **files)
        r.push()
        r.sh("checkout", "-q", "feat")

    def merge_main_dropping(self, msg, date):
        """Merges main into feat, then sets app.txt back to BODY: every line main added to it, with no conflict."""
        r = self.r
        r.sh("merge", "--no-commit", "--no-ff", "main")
        r.put("app.txt", BODY)
        r.sh("add", "-A")
        r.sh("commit", "-q", "-m", msg, date=date)


class OwnHistory(MainLineDrop, unittest.TestCase):
    """A line the branch alone added is the branch's work. Removing it later, or in a merge, is no loss."""

    def setUp(self):
        self.cut_feat("feat adds a line", app_txt=BODY + "own line one\nown line two\n")

    def main_moves(self, n, date):
        self.main_commit("main moves %d" % n, date, other_txt="o%d\n" % n)

    def merge_dropping_own_lines(self, date):
        self.merge_main_dropping("Merge main, drop my own lines", date)

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
    """The check reads every lost line of a file in one `git log -p`, never one `git log -G` per line. A merge
    that drops 20 lines of one file must cost a fixed number of git calls, not one per line."""

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


# ------------------------------------------------ own lines past position 25


OWN30 = ["own line %02d" % i for i in range(1, 31)]  # more than 25: a per-file cap of 25 would leave own lines unread
MAIN30 = ["main line %02d" % i for i in range(1, 31)]
TAIL = ["main tail %d" % i for i in range(1, 4)]  # lost after the 30 own lines, so past position 25 of the lost list


def dropped_from_parent(r, m, n, lines):
    """True when merge m's n-th parent holds `lines` in app.txt and m holds none of them."""
    held = r.sh("show", "%s^%d:app.txt" % (m, n)).split("\n")
    merged = r.sh("show", "%s:app.txt" % m).split("\n")
    return all(l in held for l in lines) and not any(l in merged for l in lines)


def mixed_merge():
    """A merge that drops 30 own lines and 3 main lines of one file from its first parent, feat. feat adds the
    own lines above `function Card`, then merges main, which adds TAIL below it. `other` branches from the base
    and holds neither kind, so the merge base has none of them. -> (repo, merge sha)."""
    card = "function Card() {}\n"
    r = base_repo()
    base = r.sh("rev-parse", "HEAD")
    r.sh("checkout", "-q", "-b", "feat")
    r.commit("feat adds own lines", app_txt=BODY + "".join(l + "\n" for l in OWN30) + card)
    r.sh("checkout", "-q", "main")
    r.commit("main adds the tail", app_txt=BODY + card + "".join(l + "\n" for l in TAIL))
    r.push()
    r.sh("checkout", "-q", "feat")
    r.sh("merge", "-q", "--no-edit", "--no-ff", "main")
    r.sh("checkout", "-q", "-b", "other", base)
    r.commit("other", other_txt="other v2\n")
    r.sh("checkout", "-q", "feat")
    r.sh("merge", "-q", "--no-commit", "--no-ff", "other")
    r.put("app.txt", BODY + card)
    r.sh("add", "-A")
    r.sh("commit", "-q", "-m", "Merge other, drop the lines")
    return r, r.sh("rev-parse", "HEAD")


class OwnLineCap(unittest.TestCase):
    """branch_only_lines reads every lost line of one file as the branch's own or not, never a capped prefix.
    A merge that drops more than 25 own lines of one file must not read as undone main work."""

    def test_a_merge_that_drops_thirty_own_lines_of_one_file_reads_clean(self):
        r, m = drop_merge(OWN30, own=True)
        self.assertTrue(dropped_from_parent(r, m, 1, OWN30), "premise: the merge drops the 30 own lines from its first parent")
        self.assertEqual(C.lost_lines(r.dir, m, ("origin/main",)), [], "own lines past position 25 read as lost")
        self.assertEqual(r.verdict(), [], "own lines past position 25 read as lost")

    def test_thirty_main_carried_lines_a_merge_drops_are_all_flagged(self):
        r, m = drop_merge(MAIN30, own=False)
        self.assertTrue(dropped_from_parent(r, m, 2, MAIN30), "premise: the merge drops the 30 main lines from its second parent")
        flagged = [l for _, _, lines in C.lost_lines(r.dir, m, ("origin/main",)) for l in lines]
        self.assertEqual(sorted(flagged), sorted(MAIN30), "main-carried lines past position 25 are not all flagged")
        text = "\n".join(r.verdict())
        for line in MAIN30:
            self.assertIn(line, text, "main-carried line missing from the verdict")

    def test_own_lines_past_the_cap_are_not_flagged_beside_main_lines_past_it(self):
        r, m = mixed_merge()
        self.assertGreater(len(OWN30), 25, "premise: the 30 own lines are more than the old 25-line cap")
        before = r.sh("show", "%s^1:app.txt" % m).split("\n")
        self.assertEqual([l for l in before if l in OWN30 or l in TAIL], OWN30 + TAIL, "premise: the first parent lists the own lines, then the 3 main lines")
        self.assertTrue(dropped_from_parent(r, m, 1, OWN30 + TAIL), "premise: the merge drops all 33 lines from its first parent")
        flagged = [l for _, _, lines in C.lost_lines(r.dir, m, ("origin/main",)) for l in lines]
        self.assertEqual([l for l in flagged if l in OWN30], [], "own lines past position 25 reported as lost, beside the main lines")
        self.assertEqual(sorted(flagged), sorted(TAIL), "the flagged lines are not exactly the 3 main lines past position 25")
        text = "\n".join(r.verdict())
        self.assertEqual([l for l in OWN30 if l in text], [], "the verdict names own lines past position 25")

    def test_thirty_own_lines_cost_the_same_git_calls_as_five(self):
        r30, m30 = drop_merge(OWN30, own=True)
        _, c30 = git_calls(lambda: C.lost_lines(r30.dir, m30, ("origin/main",)))
        r5, m5 = drop_merge(OWN30[:5], own=True)
        _, c5 = git_calls(lambda: C.lost_lines(r5.dir, m5, ("origin/main",)))
        self.assertLessEqual(len(c30) - len(c5), 3, "git calls: N=5 %d, N=30 %d, probes at N=30 %d" % (len(c5), len(c30), len(probes(c30))))
        self.assertLessEqual(len(probes(c30)), 3, "probes at N=30: %d of %d git calls" % (len(probes(c30)), len(c30)))


OWN1000 = ["own line %04d" % i for i in range(1, 1001)]  # far past any per-file cap of a realistic size
SUB_NOTE = "own note: main tail 30"  # a branch-own line that holds "main tail 30" as a substring
TAIL30 = ["main tail %02d" % i for i in range(1, 31)]


def note_merge(kept):
    """feat (the older commit) adds OWN30 and SUB_NOTE above `function Card`. main (the later commit) adds TAIL30
    below it. feat merges main, then `other` (from the base, holding neither) is merged in, and the result keeps
    the own lines and TAIL30[:kept], dropping SUB_NOTE and the rest of the tail. -> (repo, merge sha)."""
    card = "function Card() {}\n"
    r = base_repo()
    base = r.sh("rev-parse", "HEAD")
    r.sh("checkout", "-q", "-b", "feat")
    r.commit("feat adds own lines and a note", date="2025-12-01T10:00:00", app_txt=BODY + "".join(l + "\n" for l in OWN30 + [SUB_NOTE]) + card)
    r.sh("checkout", "-q", "main")
    r.commit("main adds the tail", date="2025-12-02T10:00:00", app_txt=BODY + card + "".join(l + "\n" for l in TAIL30))
    r.push()
    r.sh("checkout", "-q", "feat")
    r.sh("merge", "-q", "--no-edit", "--no-ff", "main")
    r.sh("checkout", "-q", "-b", "other", base)
    r.commit("other", other_txt="other v2\n")
    r.sh("checkout", "-q", "feat")
    r.sh("merge", "-q", "--no-commit", "--no-ff", "other")
    r.put("app.txt", BODY + "".join(l + "\n" for l in OWN30) + card + "".join(l + "\n" for l in TAIL30[:kept]))
    r.sh("add", "-A")
    r.sh("commit", "-q", "-m", "Merge other, drop the note and the tail")
    return r, r.sh("rev-parse", "HEAD")


class OwnLineScale(unittest.TestCase):
    """A per-file cap of any realistic size is far below 1000 lines. A merge that drops 1000 own lines of one
    file reads clean, so a cap of any size goes red here."""

    def test_a_merge_that_drops_a_thousand_own_lines_of_one_file_reads_clean(self):
        r, m = drop_merge(OWN1000, own=True)
        self.assertTrue(dropped_from_parent(r, m, 1, OWN1000), "premise: the merge drops the 1000 own lines from its first parent")
        self.assertEqual(C.lost_lines(r.dir, m, ("origin/main",)), [], "own lines read as lost in a merge that drops 1000 of them")
        self.assertEqual(r.verdict(), [], "the verdict flags own lines in a merge that drops 1000 of them")


class OwnLineSubstring(unittest.TestCase):
    """branch_only_lines finds a lost line's adding commit with `line in text`, a substring test over the changed
    lines of each commit. A branch-own line that holds a main line as a substring is then taken for that main
    line's adder, so the main line reads as own. The match must be whole lines."""

    def test_a_main_line_an_own_line_holds_as_a_substring_is_flagged(self):
        r, m = note_merge(29)
        self.assertTrue(dropped_from_parent(r, m, 1, [SUB_NOTE, TAIL30[29]]), "premise: the merge drops the note and main tail 30 from its first parent")
        flagged = [l for _, _, lines in C.lost_lines(r.dir, m, ("origin/main",)) for l in lines]
        self.assertEqual(sorted(flagged), [TAIL30[29]], "main tail 30 reads as own: the own note holds its text as a substring")
        self.assertTrue(r.verdict(), "the verdict reads clean though main tail 30 was dropped")

    def test_five_main_lines_dropped_beside_the_note_are_all_flagged(self):
        r, m = note_merge(25)
        dropped = TAIL30[25:]  # main tail 26 to 30
        self.assertTrue(dropped_from_parent(r, m, 1, [SUB_NOTE] + dropped), "premise: the merge drops the note and main tail 26 to 30 from its first parent")
        flagged = [l for _, _, lines in C.lost_lines(r.dir, m, ("origin/main",)) for l in lines]
        self.assertEqual(sorted(flagged), sorted(dropped), "a dropped main line reads as own: the own note holds its text as a substring")


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


class RestoredLine(MainLineDrop, unittest.TestCase):
    """A line a merge drops stays refused until a later commit on the branch puts it back in the same file, at least
    as many times as the parent had it. A restore in another file, or a partial one, clears nothing."""
    run_main = PrintedFindings.run_main

    def setUp(self):
        self.cut_feat("feat", other_txt="o2\n")

    def main_adds(self, *lines):
        self.main_commit("main adds", self.T1, app_txt=BODY + "".join(line + "\n" for line in lines))

    def merge_dropping_main_lines(self):
        self.merge_main_dropping("Merge main, drop its lines", self.T2)

    def at(self, rev, path):
        return self.r.sh("show", "%s:%s" % (rev, path))

    def test_a_dropped_line_a_later_commit_puts_back_in_the_same_file_is_green(self):
        self.main_adds("added by main")
        self.merge_dropping_main_lines()
        self.r.commit("put the line back", date=self.T2, app_txt=BODY + "added by main\n")
        self.assertIn("added by main", self.at("HEAD", "app.txt"), "premise: the head holds the line again")
        self.assertEqual(self.r.verdict(), [], "a line a later commit put back in the same file was still refused")

    def test_a_line_put_back_in_a_different_file_is_still_refused(self):  # guard
        self.main_adds("added by main")
        self.merge_dropping_main_lines()
        self.r.commit("put the line back in another file", date=self.T2, other_txt="o2\nadded by main\n")
        self.assertNotIn("added by main", self.at("HEAD", "app.txt"), "premise: the head lacks the line in app.txt")
        self.assertIn("added by main", self.at("HEAD", "other.txt"), "premise: the head holds the line in other.txt")
        got = self.r.verdict()
        self.assertTrue(got, "a line restored in another file cleared the drop")
        self.assertTrue(any(p.startswith("app.txt:") and "added by main" in p for p in got),
                        "no finding names the dropped line in app.txt: %r" % got)

    def test_a_line_main_added_twice_and_restored_once_is_still_refused(self):  # guard
        self.main_adds("twice-added line", "twice-added line")
        self.merge_dropping_main_lines()
        self.r.commit("put one copy back", date=self.T2, app_txt=BODY + "twice-added line\n")
        self.assertEqual(self.at("origin/main", "app.txt").count("twice-added line"), 2, "premise: main added the line twice")
        self.assertEqual(self.at("HEAD", "app.txt").count("twice-added line"), 1, "premise: the head holds one copy")
        got = self.r.verdict()
        self.assertTrue(got, "one restored copy of a line main added twice cleared the drop")
        self.assertTrue(any(p.startswith("app.txt:") and "twice-added line" in p for p in got),
                        "no finding names the dropped line in app.txt: %r" % got)

    def test_a_line_main_added_twice_and_restored_twice_is_green(self):
        self.main_adds("twice-added line", "twice-added line")
        self.merge_dropping_main_lines()
        self.r.commit("put both copies back", date=self.T2, app_txt=BODY + "twice-added line\ntwice-added line\n")
        self.assertEqual(self.at("HEAD", "app.txt").count("twice-added line"), 2, "premise: the head holds both copies")
        self.assertEqual(self.r.verdict(), [], "a line restored at the count main added it was still refused")

    def test_a_dropped_line_with_no_later_commit_is_refused_and_the_remedy_names_the_trailer(self):  # guard
        self.main_adds("added by main")
        self.merge_dropping_main_lines()
        self.assertNotIn("added by main", self.at("HEAD", "app.txt"), "premise: the head is the merge, which dropped the line")
        got = self.r.verdict()
        self.assertTrue(got, "a merge that dropped a line main added passed")
        self.assertTrue(any(p.startswith("app.txt:") and "added by main" in p for p in got),
                        "no finding names the dropped line in app.txt: %r" % got)
        rc, text = self.run_main(["--repo", self.r.dir, "--upstream", "origin/main"], "utf-8")
        remedy = [line for line in text.splitlines() if "put the work back" in line]
        self.assertEqual(rc, 1, "the refused merge did not exit 1")
        self.assertTrue(remedy and ("%s:" % C.TRAILER) in remedy[0],
                        "the remedy line does not name the %s trailer" % C.TRAILER)

    def test_two_dropped_lines_one_put_back_names_only_the_other(self):
        self.main_adds("restored alpha", "still missing beta")
        self.merge_dropping_main_lines()
        self.r.commit("put alpha back", date=self.T2, app_txt=BODY + "restored alpha\n")
        self.assertIn("restored alpha", self.at("HEAD", "app.txt"), "premise: the head holds the restored line")
        self.assertNotIn("still missing beta", self.at("HEAD", "app.txt"), "premise: the head lacks the second line")
        got = self.r.verdict()
        self.assertTrue(any(p.startswith("app.txt:") for p in got), "no finding names app.txt: %r" % got)
        text = "\n".join(got)
        self.assertIn("still missing beta", text, "the line the head still lacks was not named")
        self.assertNotIn("restored alpha", text, "a line a later commit put back in the same file was still named")

    def test_two_merges_that_each_drop_one_copy_of_a_line_are_not_both_cleared_by_one_restored_copy(self):
        r = self.r
        fork = r.sh("rev-parse", "HEAD")  # the feat commit: a second lane starts here, on the same base
        self.main_adds("added by main")
        self.merge_dropping_main_lines()
        merge_a = r.sh("rev-parse", "HEAD")
        r.sh("checkout", "-q", "-b", "feat2", fork)
        # its own message: the same parents, tree and date would make this the first merge's commit
        self.merge_main_dropping("Merge main into the second lane, drop its line", self.T2)
        merge_c = r.sh("rev-parse", "HEAD")
        r.sh("checkout", "-q", "feat")
        r.sh("merge", "--no-edit", "feat2", date=self.T2)
        r.commit("put the line back", date=self.T2, app_txt=BODY + "added by main\n")
        self.assertNotEqual(merge_a, merge_c, "premise: the two merges are two commits")
        self.assertNotIn("added by main", self.at(merge_a, "app.txt"), "premise: the first merge dropped the line")
        self.assertNotIn("added by main", self.at(merge_c, "app.txt"), "premise: the second merge dropped the line")
        self.assertEqual(self.at("HEAD", "app.txt").count("added by main"), 1, "premise: the head holds one copy")
        got = self.r.verdict()
        self.assertEqual(len(got), 1, "two merges each dropped one copy, the head holds one: want 1 finding, got %r" % got)
        self.assertIn("added by main", got[0], "the finding does not name the dropped line: %r" % got)

    def test_a_loss_at_a_renamed_file_is_not_cleared_by_a_later_file_recreated_at_the_old_name(self):
        r = self.r
        self.main_adds("added by main")
        r.sh("merge", "--no-commit", "--no-ff", "main")
        r.sh("mv", "app.txt", "app2.txt")
        r.put("app2.txt", BODY)  # the merge renames app.txt to app2.txt and drops the line main added to it
        r.sh("add", "-A")
        r.sh("commit", "-q", "-m", "Merge main, rename app.txt, drop its line", date=self.T2)
        merge = r.sh("rev-parse", "HEAD")
        r.commit("recreate the old name with the line", date=self.T2, app_txt=BODY + "added by main\n")
        names = r.sh("ls-tree", "--name-only", merge).split()
        self.assertIn("app2.txt", names, "premise: the merge renamed app.txt to app2.txt")
        self.assertNotIn("app.txt", names, "premise: the merge left no app.txt")
        self.assertNotIn("added by main", self.at("HEAD", "app2.txt"), "premise: the head lacks the line at the new name")
        self.assertIn("added by main", self.at("HEAD", "app.txt"), "premise: the head holds the line at the old name")
        got = self.r.verdict()
        self.assertTrue(got, "a line dropped at the new name was cleared by a file recreated at the old name")
        self.assertTrue(any("added by main" in g for g in got), "no finding names the dropped line: %r" % got)


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

    def cut_then_main_adds_the_note(self):
        """Cut `retire` from main, then main adds NOTE_LINE to the debt, then `retire` merges main in: it holds that line."""
        self.r.sh("checkout", "-q", "-b", "retire")
        self.r.put("other.txt", "branch work\n")
        self.r.sh("add", "-A")
        self.r.sh("commit", "-q", "-m", "branch work")
        self.r.sh("checkout", "-q", "main")
        self.r.put(self.DEBT, debt(PROSE) + self.NOTE_LINE)
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

    def two_cited_closes(self):
        """Two debts. DEBT: landed by a PR, then main adds NOTE_LINE after the cut; the branch deletes it, so the delete undoes
        main's line and has a finding with no cite. OTHER: on main with no PR, so its delete has no finding. Both are cited."""
        self.r.put(self.OTHER, debt("Delete the other helper once nothing reads it."))
        self.r.sh("add", "-A")
        self.r.sh("commit", "-q", "-m", "add the other debt on main with no PR")
        self.r.push()
        self.land({self.DEBT: debt(PROSE)})
        self.cut_then_main_adds_the_note()
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

    def test_a_cite_for_another_slug_does_not_excuse_the_debt_delete(self):
        self.land({self.DEBT: debt(PROSE)})
        head = self.drop(self.DEBT)
        self.assert_deleted(head, self.DEBT)
        body = self.CITE % ("another-slug", RUN_URL)
        self.assertEqual(self.scope(head, body, Runs(("success", head))), [(self.SLUG, "prose")], "scope")
        problems, notes = self.silent(head, body, Runs(("success", head)))
        self.assertTrue(self.finding(problems, self.DEBT), (problems, notes))

    def test_a_cited_run_that_failed_does_not_excuse_the_debt_delete(self):
        self.land({self.DEBT: debt(PROSE)})
        head = self.drop(self.DEBT)
        self.assert_deleted(head, self.DEBT)
        body = self.CITE % (self.SLUG, RUN_URL)
        self.assertEqual(self.scope(head, body, Runs(("failure", head))), [(self.SLUG, "red")], "scope")
        problems, notes = self.silent(head, body, Runs(("failure", head)))
        self.assertTrue(self.finding(problems, self.DEBT), (problems, notes))

    def test_a_green_run_below_the_pr_head_does_not_excuse_the_debt_delete(self):
        self.land({self.DEBT: debt(PROSE)})
        head = self.drop(self.DEBT)
        self.assert_deleted(head, self.DEBT)
        body = self.CITE % (self.SLUG, RUN_URL)
        below = self.r.sh("rev-parse", "origin/main")  # the parent of the PR head: an ancestor, not a commit at or above it
        self.assertEqual(self.scope(head, body, Runs(("success", below))), [(self.SLUG, "red")], "scope")
        problems, notes = self.silent(head, body, Runs(("success", below)))
        self.assertTrue(self.finding(problems, self.DEBT), (problems, notes))

    def test_no_run_reader_excuses_nothing(self):
        self.land({self.DEBT: debt(PROSE)})
        head = self.drop(self.DEBT)
        self.assert_deleted(head, self.DEBT)
        body = self.CITE % (self.SLUG, RUN_URL)
        self.assertEqual(self.scope(head, body, None), [(self.SLUG, "unknown")], "scope")
        problems, notes = self.silent(head, body, None)  # no run_state: the default, so the case passes the argument only if check() takes one
        self.assertTrue(self.finding(problems, self.DEBT), (problems, notes))

    def test_a_run_reader_that_raises_excuses_nothing(self):
        self.land({self.DEBT: debt(PROSE)})
        head = self.drop(self.DEBT)
        self.assert_deleted(head, self.DEBT)
        body = self.CITE % (self.SLUG, RUN_URL)
        boom = RuntimeError("the run read failed: HTTP 502")
        self.assertEqual(self.scope(head, body, Runs(boom)), [(self.SLUG, "unknown")], "scope")
        problems, notes = self.silent(head, body, Runs(boom))
        self.assertTrue(self.finding(problems, self.DEBT), (problems, notes))

    def test_a_green_cite_does_not_excuse_a_retire_test_that_fails(self):
        self.land({self.DEBT: debt(self.RED_RETIRE)})
        head = self.drop(self.DEBT)
        self.assert_deleted(head, self.DEBT)
        body = self.CITE % (self.SLUG, RUN_URL)
        self.assertEqual(self.scope(head, body, Runs(("success", head))), [(self.SLUG, "red")], "scope")
        problems, notes = self.silent(head, body, Runs(("success", head)))
        self.assertTrue(self.finding(problems, self.DEBT), (problems, notes))

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


class RevivedNote(unittest.TestCase):
    """A note the branch deleted must not come back when a merge brings the base in. The notes file merges by union (the
    real `.gitattributes` line), so a merge that conflicts at the file's end keeps the base's copy with no clash. Each of the
    first six cases runs twice: with that line, and with no `.gitattributes`, where the same merge conflicts and is resolved by
    hand. The doubled-note cases and the reworded and in-place cases run with the union line only: the doubling and the reword come from the
    union driver, which a plain merge does not use."""

    ATTRIBUTES = os.path.join(os.path.dirname(HERE), ".gitattributes")  # the real file: its union line is what is under test
    NOTES = "docs/debts/notes.md"
    HEADING = "# Notes: findings too unlikely to hit to be debts"
    UNTOUCHED = "- untouched-note: a finding the branch never touches (lint/check_untouched.py)"
    RETIRED = "- retired-note: a finding the branch retires (lint/check_retired.py)"
    OWN = "- branch-note: a finding the branch adds (lint/check_branch.py)"
    MAIN = "- main-note: a finding main adds after the cut (lint/check_main.py)"
    DOUBLED = "- doubled-note: a finding a union merge doubles (lint/check_doubled.py)"
    LATER = "- later-note: a finding main adds after the doubled note (lint/check_later.py)"
    REWORDED = "- retired-note: a finding the branch retires, reworded (lint/check_retired.py)"
    IN_PLACE = "an edit in place does not keep a note"  # the refusal's words, compared lowercased
    NONSLUG = "- AskUserQuestion gain/loss rule may refuse terse real choices: check it on real questions."  # no slug: a space before the colon
    NONSLUG_MAIN = "- a note with no slug form, appended on main (lint/check_second.py)"
    NONSLUG_EDITED = "- AskUserQuestion gain/loss rule may refuse terse real choices: check it on real questions, reworded."
    SIBLING = "- AskUserQuestion gain/loss rule may refuse terse real choices: keep it as it is."  # shares NONSLUG's first 40 characters
    SIBLING_NEW = "- AskUserQuestion gain/loss rule may refuse terse real choices: a note main adds."

    def text(self, *lines):
        return "".join(line + "\n" for line in (self.HEADING,) + lines)

    def notes_at(self, rev):
        return self.r.sh("show", "%s:%s" % (rev, self.NOTES)).splitlines()

    def start(self, union, retire=True, base=None, branch=None, main=None):
        """A base whose notes hold untouched-note and retired-note, then an unrelated main commit, so the fork point is that
        commit and not the one that added the notes. The branch deletes retired-note, or with retire False appends a line of
        its own. Main then appends main-note after retired-note, so the two edits meet at the end of the file. `base`, `branch`
        and `main` replace those notes lines (after the heading) for the cases that need other text. -> the branch's commit.
        The layout file makes the notes path docs/debts/notes.md, as RetireCite does."""
        base = (self.UNTOUCHED, self.RETIRED) if base is None else base
        if branch is None:
            branch = (self.UNTOUCHED,) if retire else (self.UNTOUCHED, self.RETIRED, self.OWN)
        main = (self.UNTOUCHED, self.RETIRED, self.MAIN) if main is None else main
        r = self.r = Repo()
        self.union = union
        r.put(".claude/layout-extras.json", json.dumps({"kinds": {}, "rolled-out": True}) + "\n")
        if union:
            shutil.copyfile(self.ATTRIBUTES, os.path.join(r.dir, ".gitattributes"))
        r.commit("notes", docs__debts__notes_md=self.text(*base))
        r.commit("unrelated main commit", other_txt="other v1\n")
        r.push()
        r.sh("checkout", "-q", "-b", "feat")
        self.assertEqual(r.sh("check-attr", "merge", "--", self.NOTES).rsplit(": ", 1)[-1], "union" if union else "unspecified",
                         "premise: this variant's driver for the notes file")
        self.retire = None
        edit = r.commit("the branch edits the notes", docs__debts__notes_md=self.text(*branch))
        if retire:
            self.retire = edit
        r.sh("checkout", "-q", "main")
        r.commit("main appends", docs__debts__notes_md=self.text(*main))
        r.push()
        r.sh("checkout", "-q", "feat")
        return edit

    def merge_main(self, final=None):
        """Merges main into the branch and commits the result. self.merged is the file git wrote before any resolution. `final`,
        when given, is the text the merge commit holds instead. -> the head sha."""
        r = self.r
        r.sh("merge", "--no-commit", "--no-ff", "main", ok=False)  # a conflict is resolved below, never left open
        with open(os.path.join(r.dir, *self.NOTES.split("/")), encoding="utf-8") as f:
            self.merged = f.read()
        self.assertEqual("<<<<<<<" in self.merged, not self.union, "premise: the merge conflicts only without the union line")
        if final is not None:
            r.put(self.NOTES, final)
        r.sh("add", "-A")
        r.sh("commit", "-q", "-m", "Merge main into the branch")
        head = r.sh("rev-parse", "HEAD")
        self.assertEqual(len(r.sh("rev-list", "--parents", "-n", "1", head).split()), 3, "premise: the head is a merge commit")
        return head

    def body(self, rev):
        """The notes lines at rev with the heading dropped: the lines a case builds the file from."""
        return self.notes_at(rev)[1:]

    def copies(self, rev):
        """How many copies of doubled-note the notes file at rev holds."""
        return self.body(rev).count(self.DOUBLED)

    def commit_notes(self, msg, lines, on_main=False):
        """Commits the notes file as the heading and `lines`, on the branch or on main. Main is pushed, so the check's upstream
        holds that commit. -> the sha."""
        if on_main:
            self.r.sh("checkout", "-q", "main")
        sha = self.r.commit(msg, docs__debts__notes_md=self.text(*lines))
        if on_main:
            self.r.push()
            self.r.sh("checkout", "-q", "feat")
        return sha

    def drop_one_copy(self, head):
        """The branch's commit that deletes the first copy of doubled-note at head. -> its sha."""
        lines = self.body(head)
        lines.remove(self.DOUBLED)
        return self.commit_notes("delete one copy of the doubled note", lines)

    def assert_refused(self, got, slug="retired-note", deleted=None):
        """One problem line names the note and the commit that deleted it: retired-note and self.retire, unless the case names
        another slug and commit."""
        deleted = deleted or self.retire
        named = [p for p in got if slug in p and deleted[:7] in p]
        self.assertTrue(named, "%s came back through the merge, and no problem names it with %s: %r" % (slug, deleted[:7], got))

    def test_union_merge_that_brings_back_a_deleted_note_is_refused(self):
        self.start(union=True)
        head = self.merge_main()
        self.assertIn(self.RETIRED, self.notes_at(head), "premise: the union merge brought retired-note back")
        self.assert_refused(self.r.verdict())

    def test_plain_merge_that_brings_back_a_deleted_note_is_refused(self):
        self.start(union=False)
        head = self.merge_main(final=self.text(self.UNTOUCHED, self.RETIRED, self.MAIN))
        self.assertIn(self.RETIRED, self.notes_at(head), "premise: the resolved plain merge brought retired-note back")
        self.assert_refused(self.r.verdict())

    def test_union_merge_that_leaves_the_deleted_note_out_passes(self):
        self.start(union=True)
        head = self.merge_main(final=self.text(self.UNTOUCHED, self.MAIN))
        self.assertIn(self.RETIRED, self.merged, "premise: the union merge had brought retired-note back before the merge commit dropped it")
        self.assertNotIn(self.RETIRED, self.notes_at(head), "premise: the merge commit leaves retired-note out")
        self.assertEqual(self.r.verdict(), [])

    def test_plain_merge_that_leaves_the_deleted_note_out_passes(self):
        self.start(union=False)
        head = self.merge_main(final=self.text(self.UNTOUCHED, self.MAIN))
        self.assertNotIn(self.RETIRED, self.notes_at(head), "premise: the resolved plain merge leaves retired-note out")
        self.assertEqual(self.r.verdict(), [])

    def test_a_note_the_branch_never_touched_passes_with_union(self):
        self.start(union=True, retire=False)
        head = self.merge_main()
        self.assertIn(self.UNTOUCHED, self.notes_at(head), "premise: untouched-note is in the head")
        self.assertEqual(self.r.verdict(), [])

    def test_a_note_the_branch_never_touched_passes_plain(self):
        self.start(union=False, retire=False)
        head = self.merge_main(final=self.text(self.UNTOUCHED, self.RETIRED, self.OWN, self.MAIN))
        self.assertIn(self.UNTOUCHED, self.notes_at(head), "premise: untouched-note is in the head")
        self.assertEqual(self.r.verdict(), [])

    def start_doubled(self):
        """The branch adds doubled-note and main adds it too, at the file's end, so the union merge of main keeps two copies."""
        return self.start(union=True, retire=False, branch=(self.UNTOUCHED, self.RETIRED, self.DOUBLED, self.OWN),
                          main=(self.UNTOUCHED, self.RETIRED, self.MAIN, self.DOUBLED))

    def test_a_dedupe_of_a_doubled_note_passes(self):
        self.start_doubled()
        head = self.merge_main()
        self.assertEqual(self.copies(head), 2, "premise: the union merge doubled doubled-note")
        head = self.drop_one_copy(head)
        self.assertEqual(self.copies(head), 1, "premise: the branch's own delete left one copy")
        self.assertEqual(self.r.verdict(), [], "one copy left by a dedupe was refused, as if a merge had revived the note")

    def test_a_dedupe_of_two_copies_on_main_passes_without_a_merge(self):
        self.start(union=True, retire=False, base=(self.UNTOUCHED, self.RETIRED, self.DOUBLED, self.DOUBLED),
                   branch=(self.UNTOUCHED, self.RETIRED, self.DOUBLED),
                   main=(self.UNTOUCHED, self.RETIRED, self.DOUBLED, self.DOUBLED, self.MAIN))
        self.assertEqual(self.copies("main"), 2, "premise: main holds two copies of doubled-note")
        self.assertEqual(self.copies("HEAD"), 1, "premise: the branch's own delete left one copy")
        self.assertEqual(self.r.verdict(), [], "a dedupe of two copies on main was refused, with no merge in the branch")

    def test_a_doubled_note_deduped_then_brought_back_by_a_merge_is_refused(self):  # control
        self.start_doubled()
        head = self.merge_main()
        dedupe = self.drop_one_copy(head)
        self.assertEqual(self.copies(dedupe), 1, "premise: the dedupe left one copy")
        self.commit_notes("main keeps two copies of the doubled note", self.body("main") + [self.DOUBLED], on_main=True)
        head = self.merge_main()
        self.assertEqual(self.copies(head), 2, "premise: the merge of main put the second copy back")
        self.assert_refused(self.r.verdict(), slug="doubled-note", deleted=dedupe)

    def test_a_doubled_note_deleted_whole_then_brought_back_by_a_merge_is_refused(self):  # control
        self.start_doubled()
        head = self.merge_main()
        whole = self.commit_notes("delete both copies of the doubled note", [l for l in self.body(head) if l != self.DOUBLED])
        self.assertEqual(self.copies(whole), 0, "premise: the branch's delete left no copy")
        self.commit_notes("main adds a note after the doubled note", self.body("main") + [self.LATER], on_main=True)
        head = self.merge_main()
        self.assertEqual(self.copies(head), 1, "premise: the union merge re-added one copy")
        self.assert_refused(self.r.verdict(), slug="doubled-note", deleted=whole)

    def test_a_dedupe_on_a_merged_in_side_branch_passes(self):
        self.start_doubled()
        head = self.merge_main()
        self.assertEqual(self.copies(head), 2, "premise: the union merge doubled doubled-note")
        self.r.sh("checkout", "-q", "-b", "side")
        lines = self.body(head)
        lines.remove(self.DOUBLED)
        self.commit_notes("side deletes one copy of the doubled note", lines)
        self.r.sh("checkout", "-q", "feat")
        self.r.sh("merge", "--no-ff", "-m", "Merge the side branch into the branch", "side")
        head = self.r.sh("rev-parse", "HEAD")
        self.assertEqual(len(self.r.sh("rev-list", "--parents", "-n", "1", head).split()), 3, "premise: the head is a merge commit")
        self.assertEqual(self.copies(head), 1, "premise: the merged side branch left one copy")
        self.assertEqual(self.r.verdict(), [], "a dedupe on a merged-in side branch was refused as a revival")

    def test_a_note_the_branch_deletes_then_re_adds_on_purpose_passes(self):  # control
        self.start(union=True)
        head = self.commit_notes("the branch re-adds retired-note on purpose", [self.UNTOUCHED, self.RETIRED])
        self.assertIn(self.RETIRED, self.notes_at(head), "premise: the re-add put retired-note back in the head")
        self.assertEqual(self.r.verdict(), [], "a note the branch deleted and then re-added on purpose was refused")

    def test_a_merge_brings_back_a_deleted_note_reworded_is_refused(self):  # control
        self.start(union=True, main=(self.UNTOUCHED, self.REWORDED, self.MAIN))
        head = self.merge_main()
        self.assertIn(self.REWORDED, self.notes_at(head), "premise: the union merge brought retired-note back reworded")
        self.assertNotIn(self.RETIRED, self.notes_at(head), "premise: the head holds no copy of the original text")
        self.assert_refused(self.r.verdict())

    def test_a_merge_brings_back_a_deleted_note_then_an_edit_in_place_is_refused(self):
        self.start(union=True)
        head = self.merge_main()
        self.assertIn(self.RETIRED, self.notes_at(head), "premise: the union merge brought retired-note back")
        self.commit_notes("reword the revived note in place", [self.REWORDED if line == self.RETIRED else line for line in self.body(head)])
        self.assertEqual(len(self.r.sh("rev-list", "--parents", "-n", "1", "HEAD").split()), 2, "premise: the reword is a non-merge commit")
        self.assertEqual(sum(line.startswith("- retired-note:") for line in self.body("HEAD")), 1,
                         "premise: the reword left one copy of retired-note")
        self.assertNotIn(self.RETIRED, self.body("HEAD"), "premise: the reword replaced the original text")
        got = self.r.verdict()
        self.assert_refused(got)
        named = [p for p in got if "retired-note" in p and self.retire[:7] in p]
        self.assertIn(self.IN_PLACE, named[0].lower(), "the refusal for retired-note does not say that an edit in place does not keep a note: %r" % named)

    def test_a_merge_brings_back_a_deleted_note_then_deleted_and_re_added_passes(self):  # control
        self.start(union=True)
        head = self.merge_main()
        self.assertIn(self.RETIRED, self.notes_at(head), "premise: the union merge brought retired-note back")
        deleted = self.commit_notes("delete the revived note again", [line for line in self.body(head) if line != self.RETIRED])
        self.assertNotIn(self.RETIRED, self.notes_at(deleted), "premise: the last commit deletes retired-note")
        self.commit_notes("re-add the note on purpose", self.body(head))
        self.assertIn(self.RETIRED, self.notes_at("HEAD"), "premise: the re-add put retired-note back in the head")
        self.assertEqual(self.r.verdict(), [], "a note a merge brought back, then deleted and re-added on purpose, was refused")

    def octopus(self):
        """Merges two side branches into the branch in one commit, so the head has three parents. Each side is cut from the
        branch's head and adds its own file. Neither touches the notes file, so the octopus strategy merges no content. -> the head sha."""
        r = self.r
        feat = r.sh("rev-parse", "HEAD")
        for name in ("side-a", "side-b"):
            r.sh("checkout", "-q", "-b", name, feat)
            r.put(name + ".txt", name + "\n")
            r.sh("add", "-A")
            r.sh("commit", "-q", "-m", "%s adds its own file" % name)
        r.sh("checkout", "-q", "feat")
        r.sh("merge", "--no-ff", "-m", "Octopus merge of two side branches", "side-a", "side-b")
        head = r.sh("rev-parse", "HEAD")
        self.assertEqual(len(r.sh("rev-list", "--parents", "-n", "1", head).split()), 4, "premise: the head is an octopus merge of three parents")
        return head

    def unknown_of(self, head):
        """The Unknown that check() raises for head, or None when check() returns a verdict."""
        try:
            C.check(self.r.dir, "origin/main", head)
        except C.Unknown as e:
            return e
        return None

    def main_on(self, head, *extra):
        """main() on the branch's repo at head, with CI unset. -> (rc, the lines it printed)."""
        with unittest.mock.patch.dict(os.environ), contextlib.redirect_stdout(io.StringIO()) as out:
            os.environ.pop("CI", None)
            rc = C.main(["--repo", self.r.dir, "--upstream", "origin/main", "--head", head, *extra])
        return rc, out.getvalue().splitlines()

    def test_an_octopus_merge_does_not_hide_a_revived_note(self):
        self.start(union=True)
        self.merge_main()
        head = self.octopus()
        e = self.unknown_of(head)
        self.assertIsNotNone(e, "premise: check() reads the octopus merge as UNKNOWN")
        self.assert_refused(getattr(e, "problems", None) or [])

    def test_an_octopus_unknown_for_a_revived_note_carries_its_notes_as_a_list(self):
        self.start(union=True)
        self.merge_main()
        head = self.octopus()
        e = self.unknown_of(head)
        self.assertIsNotNone(e, "premise: check() reads the octopus merge as UNKNOWN")
        self.assertIsInstance(getattr(e, "notes", None), list,
                              "the UNKNOWN for the octopus merge carries no .notes list: %r" % (getattr(e, "notes", None),))

    def test_main_prints_the_finding_then_unknown_and_exits_1_without_strict(self):
        self.start(union=True)
        self.merge_main()
        head = self.octopus()
        rc, lines = self.main_on(head)
        self.assertEqual(rc, 1, "main() exits 0 on an octopus merge that hides a revived note: %r" % lines)
        fail = [i for i, l in enumerate(lines) if "FAIL" in l and "retired-note" in l and self.retire[:7] in l]
        unknown = [i for i, l in enumerate(lines) if "UNKNOWN" in l]
        self.assertTrue(fail, "main() printed no FAIL line for retired-note: %r" % lines)
        self.assertTrue(unknown, "main() printed no UNKNOWN line: %r" % lines)
        self.assertLess(fail[0], unknown[0], "main() printed UNKNOWN before the FAIL line: %r" % lines)

    def test_an_octopus_merge_with_no_finding_stays_a_plain_unknown(self):  # control
        self.start(union=True, retire=False)
        self.merge_main()
        head = self.octopus()
        e = self.unknown_of(head)
        self.assertIsNotNone(e, "premise: check() reads the octopus merge as UNKNOWN")
        self.assertFalse(getattr(e, "problems", None), "an octopus merge with no finding carries findings: %r" % (getattr(e, "problems", None),))
        rc, lines = self.main_on(head)
        self.assertEqual(rc, 0, "an UNKNOWN with no finding exits 1 without --strict: %r" % lines)
        self.assertTrue(any("UNKNOWN" in l for l in lines), "main() printed no UNKNOWN line: %r" % lines)
        rc, lines = self.main_on(head, "--strict")
        self.assertEqual(rc, 1, "--strict does not exit 1 on an UNKNOWN: %r" % lines)

    def test_another_unknown_from_the_history_read_carries_no_findings(self):  # control
        self.start(union=True)
        head = self.merge_main()
        boom = C.Unknown("git cat-file failed on a read of the history: test")
        with unittest.mock.patch.object(C, "lost_lines", side_effect=boom):
            e = self.unknown_of(head)
        self.assertIsNotNone(e, "premise: the faulted read raised")
        self.assertEqual(str(e), str(boom), "a read that is not the octopus read changed its Unknown: %r" % str(e))
        self.assertFalse(getattr(e, "problems", None), "a read that is not the octopus read carries findings: %r" % (getattr(e, "problems", None),))

    def test_a_merge_brings_back_a_deleted_non_slug_note_is_refused(self):
        self.start(union=True, base=(self.UNTOUCHED, self.RETIRED, self.NONSLUG), branch=(self.UNTOUCHED, self.RETIRED),
                   main=(self.UNTOUCHED, self.RETIRED, self.NONSLUG, self.MAIN))
        head = self.merge_main()
        self.assertIn(self.NONSLUG, self.notes_at(head), "premise: the union merge brought the non-slug note back")
        self.assert_refused(self.r.verdict(), slug=self.NONSLUG[2:])

    def test_a_merge_brings_back_a_deleted_non_slug_note_in_a_file_of_only_such_notes_is_refused(self):
        self.start(union=True, base=(self.NONSLUG,), branch=(), main=(self.NONSLUG, self.NONSLUG_MAIN))
        head = self.merge_main()
        self.assertEqual(set(self.body(head)), {self.NONSLUG, self.NONSLUG_MAIN},
                         "premise: the head holds only non-slug notes, with the deleted one back")
        self.assert_refused(self.r.verdict(), slug=self.NONSLUG[2:])

    def test_a_non_slug_note_the_branch_deletes_then_re_adds_on_purpose_passes(self):  # control
        self.start(union=True, base=(self.UNTOUCHED, self.NONSLUG), branch=(self.UNTOUCHED,),
                   main=(self.UNTOUCHED, self.NONSLUG, self.MAIN))
        head = self.commit_notes("the branch re-adds the non-slug note on purpose", [self.UNTOUCHED, self.NONSLUG])
        self.assertIn(self.NONSLUG, self.notes_at(head), "premise: the re-add put the non-slug note back in the head")
        self.assertEqual(self.r.verdict(), [], "a non-slug note the branch deleted and re-added on purpose was refused")

    def test_an_in_place_edit_of_a_non_slug_note_is_not_a_revival(self):  # control
        self.start(union=True, base=(self.UNTOUCHED, self.NONSLUG, self.RETIRED),
                   branch=(self.UNTOUCHED, self.NONSLUG_EDITED, self.RETIRED),
                   main=(self.UNTOUCHED, self.NONSLUG, self.RETIRED, self.MAIN))
        head = self.merge_main()
        self.assertIn(self.NONSLUG_EDITED, self.notes_at(head), "premise: the branch's in-place edit is in the head")
        self.assertNotIn(self.NONSLUG, self.notes_at(head), "premise: the head holds no copy of the original text")
        self.assertEqual(self.r.verdict(), [], "an in-place edit of a non-slug note was refused as a revival")

    def test_a_deleted_non_slug_note_does_not_flag_a_different_note_with_the_same_start(self):  # control
        self.start(union=True, base=(self.UNTOUCHED, self.NONSLUG, self.SIBLING), branch=(self.UNTOUCHED, self.SIBLING),
                   main=(self.UNTOUCHED, self.NONSLUG, self.SIBLING, self.SIBLING_NEW))
        head = self.merge_main()
        self.assertEqual(self.body(head), [self.UNTOUCHED, self.SIBLING, self.SIBLING_NEW],
                         "premise: the head holds the sibling and the new note, not the deleted one")
        self.assertEqual(self.r.verdict(), [], "a deleted non-slug note flagged a different note that shares its first 40 characters")


class DefaultBase(unittest.TestCase):
    """With no --upstream, a local run judges the branch against its base: the upstream the branch tracks, which for a
    stacked branch is the branch it stacks on. Until then the default is origin/main. An explicit --upstream always wins.
    With no base found, the run prints the base it used and falls back to origin/main. Each fixture sets its tracking with
    --track or --no-track, so the answer does not depend on autoSetupMerge. The PR-base lookup (gh) is not fixtured here."""

    T0, T1, T2, T3, T4 = ("2026-01-01T10:00:00", "2026-01-02T10:00:00", "2026-01-03T10:00:00",
                          "2026-01-04T10:00:00", "2026-01-05T10:00:00")

    def run_main(self, argv):
        return PrintedFindings.run_main(self, argv, "utf-8")

    @staticmethod
    def findings(text):
        """The FAIL lines and their bullet lines: what a run found, without any base line it prints."""
        return [l for l in text.splitlines() if ": FAIL: " in l or l.startswith("      - ")]

    @classmethod
    def undoes_main_revert(cls, text):
        """True when a finding says a change undoes a commit whose subject names Q (main's add, or main's revert of it)."""
        return any("undoing" in l and "main adds Q" in l for l in cls.findings(text))

    @staticmethod
    def named_base(text):
        """The printed lines that name origin/main as the base the run used. The one home of that reading."""
        return [l for l in text.splitlines() if "origin/main" in l and "base" in l.lower()]

    def stacked_revert(self):
        """main adds Q. feat1, cut from main, reverts Q and is pushed. feat2 stacks on feat1 and tracks origin/feat1."""
        r = Repo()
        r.commit("base", date=self.T0, app_txt=BODY + "function Card() {}\n")
        r.push()
        q = r.commit("main adds Q", date=self.T1, app_txt=BODY + "function Card() {}\nQ1\n")
        r.push()
        r.sh("checkout", "-q", "-b", "feat1", "origin/main")
        r.sh("revert", "--no-edit", q, date=self.T2)
        r.sh("push", "-q", "origin", "feat1")
        r.sh("checkout", "-q", "-b", "feat2", "--track", "origin/feat1")
        r.commit("feat2 other", date=self.T3, other_txt="other v2\n")
        return r

    def stacked_merge_drop(self):
        """feat1 adds P1 and is pushed. feat2 stacks on feat1. feat1 then adds P2 and is pushed. feat2 merges feat1 keeping
        its own side, so P2 is dropped. P1 and P2 are on feat1 only: main never had them."""
        r = Repo()
        r.commit("base", date=self.T0, app_txt=BODY + "function Card() {}\n")
        r.push()
        r.sh("checkout", "-q", "-b", "feat1", "origin/main")
        r.commit("feat1 adds P1", date=self.T1, app_txt=BODY + "function Card() {}\nP1\n")
        r.sh("push", "-q", "origin", "feat1")
        r.sh("checkout", "-q", "-b", "feat2", "--track", "origin/feat1")
        r.commit("feat2 other", date=self.T2, other_txt="other v2\n")
        r.sh("checkout", "-q", "feat1")
        r.commit("feat1 adds P2", date=self.T3, app_txt=BODY + "function Card() {}\nP1\nP2\n")
        r.sh("push", "-q", "origin", "feat1")
        r.sh("checkout", "-q", "feat2")
        r.sh("merge", "-q", "-s", "ours", "--no-edit", "origin/feat1", date=self.T4)
        return r

    def based_on_main(self):
        """A branch cut from origin/main and tracking it. It merges main keeping its own side, so main's K1 is dropped."""
        r = Repo()
        r.commit("base", date=self.T0, app_txt=BODY + "function Card() {}\n")
        r.push()
        r.sh("checkout", "-q", "-b", "stale", "--track", "origin/main")
        r.commit("stale work", date=self.T1, other_txt="other v2\n")
        r.sh("checkout", "-q", "main")
        r.commit("main adds K1", date=self.T2, app_txt=BODY + "function Card() {}\nK1\n")
        r.push()
        r.sh("checkout", "-q", "stale")
        r.sh("merge", "-q", "-s", "ours", "--no-edit", "origin/main", date=self.T3)
        return r

    def no_base(self):
        """A local branch with no upstream, cut from local main. No base is found, so the run falls back to origin/main."""
        r = Repo()
        r.commit("base", date=self.T0, app_txt=BODY + "function Card() {}\n")
        r.push()
        r.sh("checkout", "-q", "-b", "solo", "--no-track")
        r.commit("solo work", date=self.T1, other_txt="other v2\n")
        return r

    def own_copy(self):
        """A branch cut from origin/main and pushed with -u, so it tracks its own pushed copy. Its merge of main keeps its
        own side and drops main's K1. The merge is pushed, so the branch's own copy holds the drop. main holds K1."""
        r = Repo()
        r.commit("base", date=self.T0, app_txt=BODY + "function Card() {}\n")
        r.push()
        r.sh("checkout", "-q", "-b", "selfb", "--no-track", "origin/main")
        r.commit("selfb work", date=self.T1, other_txt="other v2\n")
        r.sh("checkout", "-q", "main")
        r.commit("main adds K1", date=self.T2, app_txt=BODY + "function Card() {}\nK1\n")
        r.push()
        r.sh("checkout", "-q", "selfb")
        r.sh("merge", "-q", "-s", "ours", "--no-edit", "origin/main", date=self.T3)
        r.sh("push", "-q", "-u", "origin", "selfb")
        return r

    def pushed_as_other_name(self, local, remote, publish=True):
        """main adds Q. The branch `local` is cut at Q, gets one commit, and is pushed as `remote` with -u, so it tracks its
        own old copy under that name (the same name when local == remote). Then main reverts Q. The branch merges main keeping
        its own side, which puts Q back. That merge is pushed, unless publish is False: then it is a new local commit, ahead
        of the branch's own copy. Landing the head on main undoes the revert."""
        r = Repo()
        r.commit("base", date=self.T0, app_txt=BODY + "function Card() {}\n")
        r.push()
        q = r.commit("main adds Q", date=self.T1, app_txt=BODY + "function Card() {}\nQ1\n")
        r.push()
        r.sh("checkout", "-q", "-b", local, "--no-track", q)
        r.commit("%s work" % local, date=self.T2, other_txt="other v2\n")
        spec = "refs/heads/%s:refs/heads/%s" % (local, remote)  # full refs: a tag of the same name makes a bare name ambiguous
        r.sh("push", "-q", "-u", "origin", spec)
        r.sh("checkout", "-q", "main")
        r.sh("revert", "--no-edit", q, date=self.T3)
        r.push()
        r.sh("checkout", "-q", local)
        r.sh("merge", "-q", "-s", "ours", "--no-ff", "--no-edit", "origin/main", date=self.T4)
        if publish:
            r.sh("push", "-q", "origin", spec)
        return r

    def gone_upstream(self):
        """feat2 stacks on feat1 and tracks origin/feat1. feat1 is deleted on origin and pruned locally: the merge key stays,
        the upstream is gone."""
        r = self.stacked_revert()
        r.sh("push", "-q", "origin", "--delete", "feat1")
        r.sh("fetch", "-q", "--prune", "origin")
        return r

    def test_no_flag_judges_a_stacked_branch_against_its_base_not_main(self):
        r = self.stacked_revert()
        self.assertEqual(r.sh("rev-parse", "--abbrev-ref", "@{u}"), "origin/feat1",
                         "premise: feat2 does not track its base origin/feat1")
        _, text = self.run_main(["--repo", r.dir, "--upstream", "origin/main"])
        self.assertTrue(any("undoing" in l and "main adds Q" in l for l in self.findings(text)),
                        "premise: against main, feat1's revert of Q is a finding. Output: %r" % text)
        rc, text = self.run_main(["--repo", r.dir])
        self.assertEqual((rc, self.findings(text)), (0, []),
                         "no --upstream: feat2 was judged against origin/main, not its base origin/feat1")
        self.assertIn("silent-undo: base: origin/feat1 (the branch's tracked upstream)", text.splitlines(),
                      "no --upstream: the printed base line is not feat2's tracked upstream. Output: %r" % text)

    def test_an_explicit_upstream_prints_no_base_line(self):
        r = self.stacked_revert()
        self.assertEqual(r.sh("rev-parse", "--abbrev-ref", "@{u}"), "origin/feat1",
                         "premise: feat2 tracks origin/feat1, so the flag alone decides the base")
        rc, text = self.run_main(["--repo", r.dir, "--upstream", "origin/main"])
        self.assertTrue(self.undoes_main_revert(text),
                        "premise: --upstream origin/main still runs and finds the revert of Q. Output: %r" % text)
        self.assertEqual([l for l in text.splitlines() if l.startswith("silent-undo: base:")], [],
                         "--upstream origin/main printed a base line, so the base was not the flag's alone. Output: %r" % text)

    def test_no_flag_reports_a_line_only_the_base_added_that_a_merge_drops(self):
        r = self.stacked_merge_drop()
        self.assertEqual(r.sh("rev-parse", "--abbrev-ref", "@{u}"), "origin/feat1",
                         "premise: feat2 does not track its base origin/feat1")
        _, text = self.run_main(["--repo", r.dir, "--upstream", "origin/feat1"])
        self.assertIn("- P2", text, "premise: against its base origin/feat1, the merge drops P2. Output: %r" % text)
        rc, text = self.run_main(["--repo", r.dir])
        self.assertIn("- P2", text, "no --upstream: the merge dropped P2, a line only the base holds, and nothing reported it")
        self.assertEqual(rc, 1, "no --upstream: the run did not exit 1 on the dropped P2. Output: %r" % text)

    def test_explicit_upstream_main_still_judges_a_stacked_branch_against_main(self):  # control
        r = self.stacked_revert()
        self.assertEqual(r.sh("rev-parse", "--abbrev-ref", "@{u}"), "origin/feat1",
                         "premise: feat2 tracks origin/feat1, so the flag alone decides the base")
        rc, text = self.run_main(["--repo", r.dir, "--upstream", "origin/main"])
        self.assertEqual(rc, 1, "--upstream origin/main: the run no longer fails on the revert of Q. Output: %r" % text)
        self.assertTrue(any("undoing" in l and "main adds Q" in l for l in self.findings(text)),
                        "--upstream origin/main: the revert of Q is no longer reported")

    def test_no_flag_on_a_branch_based_on_main_reports_what_explicit_main_reports(self):  # control
        r = self.based_on_main()
        self.assertEqual(r.sh("rev-parse", "--abbrev-ref", "@{u}"), "origin/main",
                         "premise: the branch tracks origin/main")
        rc_flag, text_flag = self.run_main(["--repo", r.dir, "--upstream", "origin/main"])
        self.assertIn("- K1", text_flag, "premise: against origin/main, the merge drops K1. Output: %r" % text_flag)
        rc, text = self.run_main(["--repo", r.dir])
        self.assertEqual((rc, self.findings(text)), (rc_flag, self.findings(text_flag)),
                         "no --upstream on a branch based on main differs from --upstream origin/main")

    def test_no_flag_with_no_base_found_prints_the_base_it_used(self):
        r = self.no_base()
        self.assertEqual(r.sh("config", "--get", "branch.solo.merge", ok=False), "",
                         "premise: solo tracks no upstream")
        rc, text = self.run_main(["--repo", r.dir])
        self.assertEqual(rc, 0, "no base found: a clean branch exits %d. Output: %r" % (rc, text))
        self.assertTrue(self.named_base(text), "no base found: the run did not print the base it used (origin/main). Output: %r" % text)

    def test_a_branch_that_tracks_its_own_pushed_copy_is_judged_against_main(self):
        r = self.own_copy()
        self.assertEqual(r.sh("rev-parse", "--abbrev-ref", "@{u}"), "origin/selfb",
                         "premise: selfb does not track its own pushed copy origin/selfb")
        _, text = self.run_main(["--repo", r.dir, "--upstream", "origin/main"])
        self.assertIn("- K1", text, "premise: against origin/main, the merge drops K1. Output: %r" % text)
        rc, text = self.run_main(["--repo", r.dir])
        self.assertIn("- K1", text, "no --upstream: the branch's own pushed copy was taken as its base, so K1's drop was not judged. "
                                    "Output: %r" % text)
        self.assertTrue(self.named_base(text), "no --upstream: no printed base line names origin/main. Output: %r" % text)

    def test_a_branch_pushed_under_another_name_is_judged_against_main(self):
        r = self.pushed_as_other_name("foo", "bar")
        self.assertEqual(r.sh("rev-parse", "--abbrev-ref", "@{u}"), "origin/bar",
                         "premise: foo does not track its pushed copy origin/bar")
        _, text = self.run_main(["--repo", r.dir, "--upstream", "origin/main"])
        self.assertTrue(self.undoes_main_revert(text),
                        "premise: against origin/main, the pushed copy undoes main's revert of Q. Output: %r" % text)
        _, text = self.run_main(["--repo", r.dir])
        self.assertTrue(self.undoes_main_revert(text),
                        "no --upstream: foo was judged against its old copy origin/bar, not origin/main. Output: %r" % text)

    def test_a_tag_named_like_a_stacked_branch_does_not_hide_its_base(self):
        r = self.stacked_merge_drop()
        r.sh("tag", "feat2")  # a tag of the branch's own name, at its head
        self.assertEqual(r.sh("rev-parse", "--abbrev-ref", "@{u}"), "origin/feat1",
                         "premise: feat2 does not track its base origin/feat1")
        self.assertNotEqual(r.sh("rev-parse", "--verify", "-q", "refs/tags/feat2", ok=False), "",
                            "premise: the tag feat2 exists")
        _, text = self.run_main(["--repo", r.dir, "--upstream", "origin/feat1"])
        self.assertIn("- P2", text, "premise: against its base origin/feat1, the merge drops P2. Output: %r" % text)
        rc, text = self.run_main(["--repo", r.dir])
        self.assertIn("- P2", text, "no --upstream: with a tag named feat2, the base origin/feat1 was not used. Output: %r" % text)

    def test_a_gone_upstream_is_named_as_gone_and_judged_against_main(self):
        r = self.gone_upstream()
        self.assertEqual(r.sh("config", "--get", "branch.feat2.merge"), "refs/heads/feat1",
                         "premise: feat2 keeps its merge key")
        self.assertEqual(r.sh("rev-parse", "--verify", "-q", "refs/remotes/origin/feat1", ok=False), "",
                         "premise: origin/feat1 is pruned")
        rc, text = self.run_main(["--repo", r.dir])
        self.assertTrue([l for l in self.named_base(text) if "gone" in l],
                        "no --upstream: the printed base line does not say the upstream is gone. Output: %r" % text)
        self.assertTrue(self.undoes_main_revert(text),
                        "no --upstream: a gone upstream was not judged against origin/main. Output: %r" % text)

    def test_a_same_name_branch_ahead_of_its_own_copy_is_judged_against_main(self):
        r = self.pushed_as_other_name("foo", "foo", publish=False)
        self.assertEqual(r.sh("rev-parse", "--abbrev-ref", "@{u}"), "origin/foo",
                         "premise: foo does not track its own copy origin/foo")
        self.assertNotEqual(r.sh("rev-parse", "HEAD"), r.sh("rev-parse", "origin/foo"),
                            "premise: foo's tip is not its own copy's tip, so the local merge is ahead of the copy")
        _, text = self.run_main(["--repo", r.dir, "--upstream", "origin/main"])
        self.assertTrue(self.undoes_main_revert(text),
                        "premise: against origin/main, the local merge undoes main's revert of Q. Output: %r" % text)
        _, text = self.run_main(["--repo", r.dir])
        self.assertTrue(self.named_base(text),
                        "no --upstream: the base is not origin/main, so the own copy was taken as the base. Output: %r" % text)
        self.assertTrue(self.undoes_main_revert(text),
                        "no --upstream: the revert of Q, undone by the local merge, was not caught. Output: %r" % text)


if __name__ == "__main__":
    unittest.main()
