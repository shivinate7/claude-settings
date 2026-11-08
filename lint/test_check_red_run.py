#!/usr/bin/env python3
"""Cases for lint/check_red_run.py. Standard library only.

    python3 lint/test_check_red_run.py

A commit that adds lines to a test path carries a trailer line in its message:

    Red-run: <command> -> <N> failed on <sha>     N >= 1, sha 7 or more hex digits
    Red-run: none: <reason>                       reason non-empty

The check reads the non-merge commits in <base>..HEAD, from --base <sha>, else env BASE_SHA. A test
path is one that hooks/guard.py is_test_rel judges. When HEAD holds lint/check_red_run.py, a commit whose
parent tree lacks it predates the check, so it is not judged. A repo without the file at HEAD gets no such
exemption: every non-merge commit that is not a revert is judged.

A commit message that cites a ruling (a phrase such as `owner ruling` or `per ruling`, outside backticks) names a
home and a time in the claim's paragraph, or in a `Ruling:` trailer line. Those cases are in RulingCiteCase.

Each case builds a fixture repo under this run's folder (lint/_test_temp.py): a base commit, then
change commits on top. The check runs as the copy at lint/check_red_run.py in that repo. The cwd and
--root cases run the module by its path, from another directory. CHECK_RED_RUN_UNDER_TEST overrides the
module path, which a stub run uses.
"""
import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
MODULE = os.path.abspath(os.environ.get("CHECK_RED_RUN_UNDER_TEST") or os.path.join(HERE, "check_red_run.py"))
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import tracked_tree  # noqa: E402  copies what git lists, so no fixture lists files (testing/tracked_tree.py)

CHECK_REL = "lint/check_red_run.py"
PRODUCT_REL = "src/widgets.py"
PRODUCT_TEXT = "def widget():\n    return 1\n"
TEST_TEXT = "def test_widget():\n    assert widget() == 1\n"
GOOD = "Red-run: python3 lint/test_widgets.py -> 2 failed on abc1234"
# Every commit carries this block, as real commits do. A check that wants Red-run as the last
# trailer fails here, not on the first real commit.
ATTRIBUTION = ["Co-Authored-By: Claude <noreply@anthropic.com>",
               "Claude-Session: https://claude.ai/code/session_0000"]
MARKER = "RULING_CITE_RE"  # the string a parent's check file holds once the ruling rule has landed
MARKER_OFF = "RULING_CITE_OFF"  # the same file with the marker renamed out: a parent from before the rule
# Commit 5568b42ac, verbatim: a claim with no home and no time, in the subject and in the trailer.
INCIDENT_SUBJECT = "Drop the span-flag and two-level red cases per the owner ruling"
INCIDENT_MESSAGE = "\n".join([
    INCIDENT_SUBJECT,
    "",
    "The span-flag rule stays as documented, and expansions stay one level deep to keep the",
    "linear bound. The single-quoted two-level text stays as a green control.",
    "",
    "Red-run: none: removes two red cases the owner ruled out; the kept control adds no new claim",
    "Co-Authored-By: Claude Haiku 5.5 <noreply@anthropic.com>",
    "Claude-Session: https://claude.ai/code/session_013NEJKzjkypcToggneCjJN8",
]) + "\n"

GIT_ENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
for _name in ("BASE_SHA", "CI", "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
    GIT_ENV.pop(_name, None)  # a case sets BASE_SHA itself; the outer shell's values never leak in

RUN_FOLDER = None


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    if RUN_FOLDER and os.path.isdir(RUN_FOLDER):
        tracked_tree.rm_tree(RUN_FOLDER)  # test-temp-standard: teardown removes the run folder


def read_module():
    with open(MODULE, encoding="utf-8", newline="") as f:
        return f.read()


def check_text(marker):
    """The check file a fixture commits. With marker=True it holds the marker string. On main the ruling rule is not
    built, so the marker is a comment there: the scope holds, and the case runs the check and gets its red from the
    assert. With marker=False the string is renamed out, so the file predates the rule."""
    text = read_module()
    if not marker:
        return text.replace(MARKER, MARKER_OFF)
    return text if MARKER in text else text + "\n# %s\n" % MARKER


def ruling_message(subject, body=None, trailers=()):
    """A commit message: the subject, an optional body paragraph, then one trailer block. The block holds a valid
    Red-run line and the attribution, as real commits do, so only the ruling claim can fail a case."""
    block = "\n".join([GOOD, *trailers, *ATTRIBUTION])
    return "\n\n".join([subject, *([body] if body else []), block]) + "\n"


class Fixture(unittest.TestCase):
    """A fixture repo: a base commit, then the change commits that a case adds on top."""

    def setUp(self):
        self.tree = tempfile.mkdtemp(dir=RUN_FOLDER, prefix="crr_")
        self.addCleanup(tracked_tree.rm_tree, self.tree)
        tracked_tree.copy_tracked(self.tree, "lint", "hooks")  # the check's imports, such as hooks/guard.py
        self.serial = 0
        self.git("init", "-q")
        self.git("symbolic-ref", "HEAD", "refs/heads/main")

    def git(self, *args, input=None):
        done = subprocess.run(["git", "-C", self.tree, "-c", "user.name=test", "-c", "user.email=test@example.com",
                               "-c", "core.autocrlf=false", *args],
                              check=True, capture_output=True, text=True, env=GIT_ENV, input=input)
        return done.stdout.strip()

    def has_file(self, rev, rel):
        done = subprocess.run(["git", "-C", self.tree, "cat-file", "-e", rev + ":" + rel],
                              capture_output=True, env=GIT_ENV)
        return done.returncode == 0

    def new_test_path(self):
        """A new test file path per call, so no two commits of one case add the same lines."""
        self.serial += 1
        return "lint/test_widgets_%d.py" % self.serial

    def commit(self, subject, files, red=None, message=None):
        """Write files (a None value deletes one), commit them, return the full sha. `red` is the Red-run line.
        `message`, when given, is the whole commit message, written as it stands."""
        for rel, text in files.items():
            path = os.path.join(self.tree, *rel.split("/"))
            if text is None:
                os.remove(path)
                continue
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(text)
        if files:
            self.git("add", "--", *files)  # only the named paths join the commit
        if message is None:
            body = ([red] if red else []) + ATTRIBUTION
            message = subject + "\n\n" + "\n".join(body) + "\n"
        self.git("commit", "-q", "--allow-empty", "--cleanup=verbatim", "-F", "-", input=message)
        return self.git("rev-parse", "HEAD")

    def base(self, files=None, check=True, marker=True):
        """The base commit the check diffs from. check=False builds a parent tree from before the check landed.
        marker=False builds one whose check file lacks the ruling rule's marker string."""
        files = dict(files or {})
        if check:
            files[CHECK_REL] = check_text(marker)
        self.base_sha = self.commit("fixture base", files)
        self.assertEqual(self.has_file(self.base_sha, CHECK_REL), check)
        if check:  # the scope, asserted before a case branches on it
            held = self.git("show", self.base_sha + ":" + CHECK_REL)
            self.assertEqual(MARKER in held, marker, "the parent's check file holds the marker: %s" % marker)

    def merge(self, branch):
        self.git("merge", "-q", "--no-ff", "-m", "Merge " + branch, branch)
        return self.git("rev-parse", "HEAD")

    def lint(self, args=None, env=None, script=None, cwd=None):
        """Run the check in the fixture repo: the copy by default, or `script` by path from `cwd`.
        Returns (exit code, stdout and stderr)."""
        argv = ["--base", self.base_sha] if args is None else args
        script = script or os.path.join(self.tree, "lint", "check_red_run.py")
        done = subprocess.run([sys.executable, script, *argv],
                              cwd=cwd or self.tree, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              env=dict(GIT_ENV, **(env or {})))
        return done.returncode, done.stdout + done.stderr


class CheckCase(Fixture):
    """Cases that need the check. Each fails on main, where lint/check_red_run.py does not exist yet."""

    def setUp(self):
        self.assertTrue(os.path.isfile(MODULE), "module absent: lint/check_red_run.py")
        super().setUp()

    def assertClean(self, args=None, env=None, script=None, cwd=None):
        rc, out = self.lint(args, env, script, cwd)
        self.assertEqual(rc, 0, out)
        self.assertNotIn("Traceback", out, out)

    def assertGap(self, out, sha, subject, rel=None):
        """The output names the commit by short sha and subject. With `rel`, it also names the path the commit added on
        the sha's line."""
        short = sha[:7]
        self.assertNotIn("Traceback", out, out)
        self.assertIn(short, out, out)
        self.assertIn(subject, out, out)
        if rel is None:
            self.assertTrue(any(short in line and subject in line for line in out.splitlines()),
                            "no line names %s with its subject:\n%s" % (short, out))
            return
        self.assertTrue(any(short in line and rel in line for line in out.splitlines()),
                        "no line names %s with %s:\n%s" % (short, rel, out))

    def assertFlagged(self, sha, subject, rel, script=None, cwd=None):
        rc, out = self.lint(script=script, cwd=cwd)
        self.assertEqual(rc, 1, out)
        self.assertGap(out, sha, subject, rel)
        return out

    def scratch_repo_test_commit(self, red=None):
        """One test commit in a repo that lacks the check file at HEAD, the shape of any repo but claude-settings.
        The tree's disk copy of the script is untracked, so the case also rejects a check read from disk."""
        self.base(check=False)
        rel = self.new_test_path()
        sha = self.commit("add widget tests", {rel: TEST_TEXT}, red=red)
        self.assertFalse(self.has_file("HEAD", CHECK_REL))
        return rel, sha

    def flagged_untrailered(self):
        """Flag one test commit that carries no trailer. Returns the check's output."""
        self.base()
        rel = self.new_test_path()
        sha = self.commit("add widget tests", {rel: TEST_TEXT})
        return self.assertFlagged(sha, "add widget tests", rel)

    def test_untrailered_test_commit_is_flagged(self):
        out = self.flagged_untrailered()
        # The check's message states both trailer forms, and how to add a trailer to a commit.
        self.assertIn("Red-run: <command> -> <N> failed on <sha>", out, out)
        self.assertIn("Red-run: none: <reason>", out, out)
        self.assertIn("reword", out, out)

    def test_remedy_names_no_force_or_interactive_route(self):
        out = self.flagged_untrailered()
        # The sessions cannot run a forced push or an interactive rebase.
        self.assertIsNone(re.search(r"--force|\s-f\b", out), "remedy names a forced push:\n" + out)
        self.assertIsNone(re.search(r"rebase\s+(-i\b|--interactive)", out),
                          "remedy names an interactive rebase:\n" + out)
        self.assertIsNone(re.search(r"(?:^|[\s`])\+[\w/:]", out), "remedy names a + refspec:\n" + out)

    def test_remedy_amend_carries_a_message(self):
        out = self.flagged_untrailered()
        self.assertIn("--amend", out, "remedy names no amend route for the last commit:\n" + out)
        # An amend with no -m opens an editor, which a session cannot drive.
        for amend in re.finditer(r"--amend", out):
            segment = re.split(r"[`\n]", out[amend.end():], maxsplit=1)[0]
            self.assertIsNotNone(re.search(r"(?<![\w-])-m\b|--message\b", segment),
                                 "remedy names an amend with no -m:\n" + out)

    def test_remedy_names_plain_push(self):
        out = self.flagged_untrailered()
        pushes = re.findall(r"git push[^`\n]*", out)
        self.assertTrue(any(not re.search(r"--force|\s-f\b", push) for push in pushes),
                        "remedy names no git push without a force flag:\n" + out)

    def test_remedy_names_cherry_pick_route(self):
        out = self.flagged_untrailered()
        # A pushed older commit goes onto a new branch by cherry-pick, since an interactive rebase cannot run.
        self.assertIn("cherry-pick", out, "remedy names no cherry-pick route for a pushed older commit:\n" + out)

    def test_valid_red_run_trailer_passes(self):
        for red in (GOOD, "Red-run: python3 lint/test_widgets.py -> 1 failed on abcdef1",
                    "Red-run: python3 lint/test_widgets.py -> 1 failed on " + "a" * 40):
            with self.subTest(red=red):
                self.base()
                self.commit("add widget tests", {self.new_test_path(): TEST_TEXT}, red=red)
                self.assertClean()

    def test_none_with_a_reason_passes(self):
        self.base()
        self.commit("re-point widget fixtures", {self.new_test_path(): TEST_TEXT},
                    red="Red-run: none: re-points fixtures")
        self.assertClean()

    def test_none_without_a_reason_is_flagged(self):
        for red in ("Red-run: none", "Red-run: none:", "Red-run: none:   "):
            with self.subTest(red=red):
                self.base()
                rel = self.new_test_path()
                sha = self.commit("add widget tests", {rel: TEST_TEXT}, red=red)
                self.assertFlagged(sha, "add widget tests", rel)

    def test_zero_failures_is_flagged(self):
        self.base()
        rel = self.new_test_path()
        sha = self.commit("add widget tests", {rel: TEST_TEXT},
                          red="Red-run: python3 lint/test_widgets.py -> 0 failed on abc1234")
        self.assertFlagged(sha, "add widget tests", rel)

    def test_short_or_missing_sha_is_flagged(self):
        for red in ("Red-run: python3 lint/test_widgets.py -> 1 failed on abc123",
                    "Red-run: python3 lint/test_widgets.py -> 1 failed"):
            with self.subTest(red=red):
                self.base()
                rel = self.new_test_path()
                sha = self.commit("add widget tests", {rel: TEST_TEXT}, red=red)
                self.assertFlagged(sha, "add widget tests", rel)

    def test_commit_that_only_deletes_test_lines_passes(self):
        rel = "lint/test_trim.py"
        self.base({rel: "def test_a():\n    assert 1\n    assert 2\n"})
        self.commit("trim widget asserts", {rel: "def test_a():\n    assert 1\n"})
        self.assertClean()
        self.base({rel: "def test_b():\n    assert 3\n"})
        self.commit("delete widget test file", {rel: None})
        self.assertClean()

    def test_product_only_commit_passes(self):
        self.base()
        self.commit("change widget product", {PRODUCT_REL: PRODUCT_TEXT})
        self.assertClean()

    def test_test_and_product_in_one_commit_is_flagged(self):
        self.base()
        rel = self.new_test_path()
        sha = self.commit("change widgets and tests", {PRODUCT_REL: PRODUCT_TEXT, rel: TEST_TEXT})
        self.assertFlagged(sha, "change widgets and tests", rel)

    def test_bad_commit_is_named_before_a_good_head(self):
        self.base()
        rel = self.new_test_path()
        bad = self.commit("add widget tests", {rel: TEST_TEXT})
        self.commit("change widget product", {PRODUCT_REL: PRODUCT_TEXT})
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertGap(out, bad, "add widget tests", rel)
        self.assertNotIn("change widget product", out, out)  # only a gap prints a subject; the range is read

    def test_merge_of_a_tested_side_passes(self):
        self.base()
        rel = self.new_test_path()
        self.git("checkout", "-q", "-b", "side")
        self.commit("add widget tests", {rel: TEST_TEXT}, red=GOOD)
        self.git("checkout", "-q", "main")
        self.commit("change widget product", {PRODUCT_REL: PRODUCT_TEXT})
        self.merge("side")  # brings in the test lines, and is not judged itself
        self.assertClean()

    def test_merge_flags_its_untrailered_side_commit_not_the_merge(self):
        self.base()
        rel = self.new_test_path()
        self.git("checkout", "-q", "-b", "side")
        side = self.commit("add widget tests", {rel: TEST_TEXT})
        self.git("checkout", "-q", "main")
        self.commit("change widget product", {PRODUCT_REL: PRODUCT_TEXT})
        self.merge("side")
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertGap(out, side, "add widget tests", rel)
        self.assertNotIn("Merge side", out, out)  # only a gap prints a subject, so the merge stays unnamed

    def test_commit_before_the_check_landed_is_not_judged(self):
        self.base(check=False)
        landed = self.commit("land the red-run check", {CHECK_REL: read_module(), self.new_test_path(): TEST_TEXT})
        self.assertFalse(self.has_file(self.base_sha, CHECK_REL))  # the landing commit's parent lacks the check
        self.assertClean()
        rel = self.new_test_path()
        later = self.commit("add a second widget test", {rel: TEST_TEXT})
        self.assertTrue(self.has_file(landed, CHECK_REL))  # the next commit's parent has the check
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertGap(out, later, "add a second widget test", rel)
        self.assertNotIn(landed[:7], out, out)

    def test_untrailered_test_commit_in_repo_without_check_is_flagged(self):
        """No rollout exemption without the check file at HEAD. The script runs by its absolute path, from the scratch repo."""
        rel, sha = self.scratch_repo_test_commit()
        self.assertFlagged(sha, "add widget tests", rel, script=MODULE, cwd=self.tree)

    def test_trailered_test_commit_in_repo_without_check_passes(self):
        """The same scratch repo, with a valid trailer on its test commit, is green. The script runs by its absolute path."""
        self.scratch_repo_test_commit(red=GOOD)
        self.assertClean(script=MODULE, cwd=self.tree)

    def test_files_that_only_look_like_tests_are_not_judged(self):
        self.base()
        self.commit("add contest helpers", {"src/contest.py": "def contest():\n    return 1\n",
                                            "src/attest.py": "def attest():\n    return 1\n"})
        self.assertClean()

    def test_file_in_a_test_folder_is_a_test_path(self):
        self.base()
        sha = self.commit("add roadmap test helpers", {"tests/helpers.py": "def helper():\n    return 1\n"})
        self.assertFlagged(sha, "add roadmap test helpers", "tests/helpers.py")

    def test_unreadable_base_exits_two_as_unknown(self):
        self.base()
        self.commit("add widget tests", {self.new_test_path(): TEST_TEXT})  # a real finding, so 0 would be wrong
        for args, env in ((["--base", "0" * 40], None), ([], {"BASE_SHA": "1" * 40})):
            with self.subTest(args=args, env=env):
                rc, out = self.lint(args, env)
                self.assertEqual(rc, 2, out)
                self.assertIn("unknown", out.lower(), out)
                self.assertNotIn("Traceback", out, out)

    def test_base_comes_from_base_sha_without_a_flag(self):
        self.base()
        rel = self.new_test_path()
        sha = self.commit("add widget tests", {rel: TEST_TEXT})
        rc, out = self.lint([], {"BASE_SHA": self.base_sha})
        self.assertEqual(rc, 1, out)
        self.assertGap(out, sha, "add widget tests", rel)

    def test_check_reads_the_repo_it_is_run_in(self):
        """The repo comes from the current directory, not from the checkout that holds the script."""
        self.base()
        rel = self.new_test_path()
        sha = self.commit("add widget tests", {rel: TEST_TEXT})
        rc, out = self.lint(script=MODULE, cwd=self.tree)
        self.assertEqual(rc, 1, "the check must read the repo it runs in, not its own checkout:\n" + out)
        self.assertGap(out, sha, "add widget tests", rel)

    def test_root_flag_names_the_repo_to_read(self):
        """--root picks the repo whatever the current directory is. The cwd here is outside any repo."""
        self.base()
        rel = self.new_test_path()
        sha = self.commit("add widget tests", {rel: TEST_TEXT})
        cwd = tempfile.mkdtemp(dir=RUN_FOLDER, prefix="cwd_")
        self.addCleanup(tracked_tree.rm_tree, cwd)
        rc, out = self.lint(["--root", self.tree, "--base", self.base_sha], script=MODULE, cwd=cwd)
        self.assertEqual(rc, 1, out)
        self.assertNotIn("usage", out, out)
        self.assertGap(out, sha, "add widget tests", rel)

    def test_revert_of_a_test_deletion_is_not_judged(self):
        """A revert re-adds the lines it undoes. Its message carries the This reverts commit line, not a trailer."""
        rel = "lint/test_trim.py"
        self.base({rel: "def test_a():\n    assert 1\n    assert 2\n"})
        trim = self.commit("trim widget asserts", {rel: "def test_a():\n    assert 1\n"})
        self.git("revert", "--no-edit", trim)
        self.assertIn("This reverts commit ", self.git("log", "-1", "--format=%B"))  # the case is a revert
        self.assertClean()

    def test_reapply_of_a_revert_is_not_judged(self):
        """A revert of a revert re-adds the test file. It carries the This reverts commit line, not a trailer."""
        rel = self.new_test_path()
        self.base()
        added = self.commit("add widget tests", {rel: TEST_TEXT}, red=GOOD)
        self.git("revert", "--no-edit", added)
        self.git("revert", "--no-edit", "HEAD")  # the reapply: it re-adds the test file
        self.assertIn("This reverts commit ", self.git("log", "-1", "--format=%B"))  # the case is a reapply
        self.assertTrue(self.has_file("HEAD", rel))
        self.assertClean()

    def test_normal_untrailered_commit_after_a_revert_is_still_flagged(self):
        """The revert exemption covers the revert commit alone. A normal test commit after it is still a gap."""
        rel = "lint/test_trim.py"
        self.base({rel: "def test_a():\n    assert 1\n    assert 2\n"})
        trim = self.commit("trim widget asserts", {rel: "def test_a():\n    assert 1\n"})
        self.git("revert", "--no-edit", trim)
        normal = self.new_test_path()
        sha = self.commit("add widget tests", {normal: TEST_TEXT})
        rc, out = self.lint()
        self.assertEqual(rc, 1, out)
        self.assertGap(out, sha, "add widget tests", normal)


class RulingCiteCase(CheckCase):
    """A commit message that cites a ruling names a home and a time. The incident message, a claim with a home and no
    time, and a claim with a time and no home are red on main, where the check does not read ruling claims. Each assert
    names its cause. The controls pass on main as well."""

    def assertRulingFlagged(self, sha, subject, cause):
        rc, out = self.lint()
        self.assertEqual(rc, 1, cause + ":\n" + out)
        self.assertGap(out, sha, subject)
        line = next(line for line in out.splitlines() if sha[:7] in line and subject in line)
        self.assertNotIn("Red-run", line, cause + ":\n" + out)  # the flag names the claim, not a missing trailer

    def ruling_commit(self, subject, message):
        """A commit that adds a test path, so the trailer rule is in play too. Returns its sha."""
        return self.commit(subject, {self.new_test_path(): TEST_TEXT}, message=message)

    def test_incident_message_with_a_bare_claim_is_flagged(self):
        """Commit 5568b42ac, verbatim: the subject and the trailer cite a ruling with no home and no time."""
        self.base()
        sha = self.ruling_commit(INCIDENT_SUBJECT, INCIDENT_MESSAGE)
        self.assertRulingFlagged(sha, INCIDENT_SUBJECT, "a claim with no home and no time is not flagged")

    def test_owner_ruling_with_a_home_and_no_time_is_flagged(self):
        self.base()
        subject = "Drop the widget tests"
        sha = self.ruling_commit(subject, ruling_message(subject, body="Per the owner's ruling, item 359 b."))
        self.assertRulingFlagged(sha, subject, "a claim with a home and no time is not flagged")

    def test_per_ruling_with_a_time_and_no_home_is_flagged(self):
        self.base()
        subject = "Drop the widget tests"
        sha = self.ruling_commit(subject, ruling_message(subject, body="Dropped per ruling at 2026-11-08 08:15 CST."))
        self.assertRulingFlagged(sha, subject, "a claim with a time and no home is not flagged")

    def test_full_cite_in_the_claim_paragraph_passes(self):
        """Each home form, with a full stamp. The claim and its cite share one paragraph."""
        cites = ("item 359 b", "step:ruling-cite-in-commit", "decision ruling-cite-in-commit",
                 "decision `ruling-cite-in-commit`", "rule:outcomes-grant-covers-named-act")
        for cite in cites:
            with self.subTest(cite=cite):
                self.base()
                subject = "Drop the widget tests"
                self.ruling_commit(subject, ruling_message(
                    subject, body="Per the owner ruling, %s, 2026-11-08 08:15 CST." % cite))
                self.assertClean()

    def test_clock_time_and_an_owners_apostrophe_pass(self):
        """A clock-only time, and an apostrophe in 'owner's'. The quote is text, so the cite still counts."""
        self.base()
        subject = "Drop the widget tests"
        self.ruling_commit(subject, ruling_message(subject, body="Per the owner's ruling, item 359 b, 08:15 CST."))
        self.assertClean()

    def test_full_cite_in_a_ruling_trailer_passes(self):
        """The claim sits in the subject. The cite sits in a Ruling: trailer line."""
        self.base()
        subject = "Drop the widget tests per the owner ruling"
        self.ruling_commit(subject, ruling_message(subject, trailers=["Ruling: item 359 b, 2026-11-08 08:15 CST"]))
        self.assertClean()

    def test_message_without_a_ruling_phrase_passes(self):
        self.base()
        subject = "Drop the widget tests"
        self.ruling_commit(subject, ruling_message(subject, body="The widget tests repeat the widget checks."))
        self.assertClean()

    def test_ruled_out_and_a_ruling_name_pass(self):
        """No owner, so 'ruled out' is not a claim. 'ruling-kind' is a name, not a ruling phrase."""
        self.base()
        subject = "Add the ruling-kind check cases"
        body = "The ruling-kind check ruled out a cause: the disk copy."
        self.ruling_commit(subject, ruling_message(subject, body=body))
        self.assertClean()

    def test_claim_inside_backticks_passes(self):
        """Inline code is a name. The span holds the phrase in a subject, in a line, and across a line break."""
        cases = (("Refuse `owner ruling` with no cite", None),
                 ("Refuse claims with no cite", "Refuse `owner ruling` with no cite."),
                 ("Refuse claims with no cite", "A claim such as `owner\nruling` is a name."))
        for subject, body in cases:
            with self.subTest(subject=subject, body=body):
                self.base()
                self.ruling_commit(subject, ruling_message(subject, body=body))
                self.assertClean()

    def test_revert_carrying_the_incident_text_passes(self):
        """A revert says This reverts commit. Its subject copies the incident subject, which cites the ruling."""
        rel = "lint/test_trim.py"
        self.base({rel: "def test_a():\n    assert 1\n    assert 2\n"})
        trim = self.commit(INCIDENT_SUBJECT, {rel: "def test_a():\n    assert 1\n"}, message=INCIDENT_MESSAGE)
        self.base_sha = trim  # the range is the revert alone
        self.git("revert", "--no-edit", trim)
        self.assertIn("This reverts commit ", self.git("log", "-1", "--format=%B"))  # the case is a revert
        self.assertClean()

    def test_incident_text_on_a_parent_without_the_marker_passes(self):
        """The rollout rule: a parent whose check file lacks the marker is not judged. Red case 1 is the same message on
        a parent that holds it. The script runs from this checkout, by its absolute path, against the fixture repo."""
        self.base(marker=False)
        self.ruling_commit(INCIDENT_SUBJECT, INCIDENT_MESSAGE)
        self.assertClean(script=MODULE, cwd=self.tree)


if __name__ == "__main__":
    unittest.main()
