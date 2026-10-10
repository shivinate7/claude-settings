#!/usr/bin/env python3
"""Fixture suite for lint/check_silent_undo.py. Run: python3 lint/test_check_silent_undo.py

Every case builds a throwaway repo with a local `origin` and asks the check for a verdict.
Red cases come from two real incidents: a squash that carried the pre-deletion copy of a file
(banchi, a revert nobody wrote), and a merge that dropped a parent's added line (q_max).
"""
import contextlib, io, os, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "merge"))
import check_silent_undo as C  # noqa: E402

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

    def test_a_bare_trailer_excuses_nothing(self):
        self.pr_deletes_block()
        r = self.r
        r.sh("checkout", "-q", "-b", "bare")
        r.sh("revert", "--no-edit", "-m", "1", "main")
        r.sh("commit", "-q", "--amend", "-m", "Bring it back\n\nDrops-lines: app.txt")
        self.assertTrue(r.verdict())

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
    """The owner's incident, single-parent form: main gained lines after the branch was cut, and
    the branch carries a version without them. Dates are fixed so a rebase keeps the cut."""
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
        """Cry-wolf guard: lines main gained BEFORE the branch was cut may be removed on purpose."""
        r = self.r
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
    """A stale value overwrite is the incident in its smallest form: A changed one value line, and
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

    def test_a_failed_read_of_the_adding_commit_counts_the_line(self):
        r = Repo()
        r.commit("base", date="2025-12-01T10:00:00", a_txt="x\n")
        self.assertFalse(C.branch_only(r.dir, "HEAD", ["nosuchrev"], "a.txt", "x", ["HEAD"]))


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


if __name__ == "__main__":
    unittest.main()
