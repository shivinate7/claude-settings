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

A commit also carries a Verified line, which says how the commit was verified:

    Verified: <command> -> <verdict>              a command that ran, and its verdict
    Verified: none: <reason>                      no command ran; the reason is not empty

Observe mode: a commit with no valid Verified line prints a gap line, and the exit code stays 0. Only a
Red-run gap sets exit 1. A merge and a revert are not judged. A repo whose HEAD does not carry the Verified
rollout judges no Verified line.

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
VERIFIED = "Verified: python3 lint/test_widgets.py -> PASS"  # the default Verified line of a fixture commit
GADGET_PATH = "src/gadget.py"
GADGET_TEXT = "def gadget():\n    return 2\n"
PRE_ROLLOUT_CHECK = "# the check file before the Verified rollout\n"  # a check file with no Verified rollout in it
ROLLOUT_MARKER = "verified-trailer-rollout-1"  # the string a check file holds once the Verified rollout landed
# Runs lint/check_red_run.py by path. A `fail` run makes the git call named by argv[2] exit 128, a read git cannot
# finish. A `count` run counts that call's starts. A grep counts only when it names the check file: that is a Verified read.
PROBE = (
    "import importlib.util, subprocess, sys\n"
    "spec = importlib.util.spec_from_file_location('check_red_run', sys.argv[1])\n"
    "module = importlib.util.module_from_spec(spec)\n"
    "spec.loader.exec_module(module)\n"
    "watch, mode = sys.argv[2], sys.argv[3]\n"
    "real, starts = module._nowindow.run, []\n"
    "def watched(argv):\n"
    "    return argv[:2] == ['git', watch] and (watch != 'grep' or module.SELF_REL in argv)\n"
    "def run(argv, *args, **kwargs):\n"
    "    if watched(argv):\n"
    "        starts.append(argv)\n"
    "        if mode == 'fail':\n"
    "            return subprocess.CompletedProcess(argv, 128, '', 'fatal: simulated failure of git ' + watch)\n"
    "    return real(argv, *args, **kwargs)\n"
    "module._nowindow.run = run\n"
    "rc = module.main(sys.argv[4:])\n"
    "print('PROBE_EXIT=%d' % rc)\n"
    "print('PROBE_STARTS=%d' % len(starts))\n"
)
# Every commit carries this block, as real commits do. A check that wants Red-run as the last
# trailer fails here, not on the first real commit.
ATTRIBUTION = ["Co-Authored-By: Claude <noreply@anthropic.com>",
               "Claude-Session: https://claude.ai/code/session_0000"]

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

    def commit(self, subject, files, red=None, verified=VERIFIED):
        """Write files (a None value deletes one), commit them, return the full sha. `red` is the Red-run line.
        `verified` is the Verified line: the default is a valid one, and None leaves the line out."""
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
        body = ([red] if red else []) + ([verified] if verified else []) + ATTRIBUTION
        self.git("commit", "-q", "--allow-empty", "--cleanup=verbatim", "-F", "-",
                 input=subject + "\n\n" + "\n".join(body) + "\n")
        return self.git("rev-parse", "HEAD")

    def base(self, files=None, check=True, check_text=None):
        """The base commit the check diffs from. check=False builds a parent tree from before the check landed.
        check_text, when set, is the check file's text in place of the current module."""
        files = dict(files or {})
        if check:
            files[CHECK_REL] = read_module() if check_text is None else check_text
        self.base_sha = self.commit("fixture base", files)
        self.assertEqual(self.has_file(self.base_sha, CHECK_REL), check)

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
    """Cases for lint/check_red_run.py, the check that reads each Red-run trailer."""

    def setUp(self):
        self.assertTrue(os.path.isfile(MODULE), "module absent: lint/check_red_run.py")
        super().setUp()

    def assertClean(self, args=None, env=None, script=None, cwd=None):
        rc, out = self.lint(args, env, script, cwd)
        self.assertEqual(rc, 0, out)
        self.assertNotIn("Traceback", out, out)

    def assertGap(self, out, sha, subject, rel):
        """The output names the commit by short sha and subject, and names the path it added on the sha's line."""
        short = sha[:7]
        self.assertNotIn("Traceback", out, out)
        self.assertIn(short, out, out)
        self.assertIn(subject, out, out)
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

    def pending_judge(self, message, rel):
        """judge() on one commit the call has not made yet, with test path `rel` staged. The range is empty, so only
        the pending row can name a gap. The module is loaded by path (MODULE), so CHECK_RED_RUN_UNDER_TEST still applies.
        Returns one list of fields per row."""
        probe = ("import importlib.util, sys\n"
                 "spec = importlib.util.spec_from_file_location('check_red_run', sys.argv[1])\n"
                 "module = importlib.util.module_from_spec(spec)\n"
                 "spec.loader.exec_module(module)\n"
                 "found, _last = module.judge(sys.argv[2], 'HEAD', 'HEAD', pending=[(sys.argv[3], [sys.argv[4]])])\n"
                 "for row in found:\n"
                 "    print('\\t'.join(row))\n")
        done = subprocess.run([sys.executable, "-c", probe, MODULE, self.tree, message, rel],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", env=GIT_ENV)
        self.assertEqual(done.returncode, 0, done.stderr)
        return [line.split("\t") for line in done.stdout.splitlines()]

    def test_pending_revert_of_a_test_commit_is_not_judged(self):
        """A commit made earlier in the same call whose message carries git's This reverts commit line is no gap,
        as a landed revert is not (decision red-run-trailer-on-test-commits, item 7). The next case is the control."""
        self.base()
        found = self.pending_judge("Revert \"add widget tests\"\n\nThis reverts commit abc1234.\n", self.new_test_path())
        self.assertEqual(found, [], "a pending revert of a test commit is judged, want no row")

    def test_pending_plain_test_commit_is_judged(self):
        """Control: the same test path under a plain message is one pending gap, shown as sha new."""
        self.base()
        rel = self.new_test_path()
        found = self.pending_judge("add widget tests\n", rel)
        self.assertEqual(found, [["new", "add widget tests", rel]], "a pending plain test commit is not one gap row")


class VerifiedCase(Fixture):
    """Cases for the Verified line: each commit says how it was verified. In observe mode a gap prints and the exit
    code stays 0. A case that expects a listing also lists an untrailered control commit, so a red shows the listing
    missing, never a crash. A control is green on the old code too and says so in its docstring."""

    def names_verified(self, out, sha):
        """True when an output line says Verified and names the commit by its short sha."""
        return any("Verified" in line and sha[:7] in line for line in out.splitlines())

    def assertListed(self, out, sha, subject):
        """Scope before subject: a line says Verified and names the commit by short sha. Then that line names the subject."""
        lines = [line for line in out.splitlines() if "Verified" in line and sha[:7] in line]
        self.assertTrue(lines, "no Verified line names %s:\n%s" % (sha[:7], out))
        self.assertIn(subject, lines[0], "the Verified line for %s does not name its subject:\n%s" % (sha[:7], out))

    def assertNotListed(self, out, sha, why):
        self.assertFalse(self.names_verified(out, sha), "%s:\n%s" % (why, out))

    def test_commit_without_a_verified_line_is_listed_and_exit_stays_zero(self):
        self.base()
        sha = self.commit("change widget product", {PRODUCT_REL: PRODUCT_TEXT}, verified=None)
        rc, out = self.lint()
        self.assertEqual(rc, 0, "observe mode: a Verified gap must leave the exit code at 0:\n" + out)
        self.assertListed(out, sha, "change widget product")

    def test_test_commit_with_a_red_run_and_no_verified_line_keeps_exit_zero(self):
        self.base()
        rel = self.new_test_path()
        sha = self.commit("add widget tests", {rel: TEST_TEXT}, red=GOOD, verified=None)
        rc, out = self.lint()
        self.assertEqual(rc, 0, "a Verified gap must not set the exit code when the Red-run line is valid:\n" + out)
        self.assertListed(out, sha, "add widget tests")

    def test_verified_command_and_verdict_passes(self):
        self.base()
        passing = self.commit("change widget product", {PRODUCT_REL: PRODUCT_TEXT},
                              verified="Verified: python3 lint/test_widgets.py -> PASS")
        control = self.commit("change gadget product", {GADGET_PATH: GADGET_TEXT}, verified=None)
        rc, out = self.lint()
        self.assertEqual(rc, 0, out)
        self.assertListed(out, control, "change gadget product")  # control: the range does produce a listing
        self.assertNotListed(out, passing, "a commit with a Verified command and verdict is listed as a gap")

    def test_verified_none_with_a_reason_passes(self):
        self.base()
        passing = self.commit("change widget product", {PRODUCT_REL: PRODUCT_TEXT},
                              verified="Verified: none: re-points widget fixtures")
        control = self.commit("change gadget product", {GADGET_PATH: GADGET_TEXT}, verified=None)
        rc, out = self.lint()
        self.assertEqual(rc, 0, out)
        self.assertListed(out, control, "change gadget product")  # control: the range does produce a listing
        self.assertNotListed(out, passing, "a commit with Verified none and a reason is listed as a gap")

    def test_bare_verified_none_is_listed(self):
        self.base()
        made = []
        for n, verified in enumerate(("Verified: none", "Verified: none:", "Verified: none:   ")):
            subject = "change gadget %d" % n
            sha = self.commit(subject, {"src/gadget_%d.py" % n: "def gadget_%d():\n    return %d\n" % (n, n)}, verified=verified)
            made.append((sha, subject, verified))
        rc, out = self.lint()
        self.assertEqual(rc, 0, out)
        for sha, subject, verified in made:
            with self.subTest(verified=verified):
                self.assertListed(out, sha, subject)

    def test_merge_commit_is_not_judged(self):
        self.base()
        self.git("checkout", "-q", "-b", "side")
        side = self.commit("change gadget product", {GADGET_PATH: GADGET_TEXT}, verified=None)
        self.git("checkout", "-q", "main")
        self.commit("change widget product", {PRODUCT_REL: PRODUCT_TEXT})
        merged = self.merge("side")
        rc, out = self.lint()
        self.assertEqual(rc, 0, out)
        self.assertListed(out, side, "change gadget product")  # control: the side commit is judged
        self.assertNotListed(out, merged, "a merge commit is listed as a Verified gap")

    def test_revert_commit_is_not_judged(self):
        self.base()
        self.commit("change gadget product", {GADGET_PATH: GADGET_TEXT}, verified=None)
        self.git("revert", "--no-edit", "HEAD")
        reverted = self.git("rev-parse", "HEAD")
        self.assertIn("This reverts commit ", self.git("log", "-1", "--format=%B"))  # scope: the case is a revert
        control = self.commit("change widget product", {PRODUCT_REL: PRODUCT_TEXT}, verified=None)
        rc, out = self.lint()
        self.assertEqual(rc, 0, out)
        self.assertListed(out, control, "change widget product")  # control: a plain commit in the range is judged
        self.assertNotListed(out, reverted, "a revert commit is listed as a Verified gap")

    def test_verified_check_starts_at_the_commit_after_the_landing(self):
        """The landing commit's parent holds a check file with no Verified rollout. The file alone does not start the check."""
        self.base(check_text=PRE_ROLLOUT_CHECK)
        landing = self.commit("land the Verified check", {CHECK_REL: read_module()}, verified=None)
        self.assertTrue(self.has_file(self.base_sha, CHECK_REL))  # the landing commit's parent holds a check file
        later = self.commit("change widget product", {PRODUCT_REL: PRODUCT_TEXT}, verified=None)
        self.assertTrue(self.has_file(landing, CHECK_REL))  # the next commit's parent holds the check too
        rc, out = self.lint()
        self.assertEqual(rc, 0, out)
        self.assertListed(out, later, "change widget product")
        self.assertNotListed(out, landing, "the landing commit's parent has no Verified rollout, yet the landing commit is listed")

    def test_every_untrailered_commit_in_a_long_range_is_listed(self):
        """Full-size state: 25 commits with no Verified line, each one a gap."""
        self.base()
        shas = [self.commit("change part %d" % i, {"src/part_%d.py" % i: "def part():\n    return %d\n" % i}, verified=None)
                for i in range(25)]
        rc, out = self.lint()
        self.assertEqual(rc, 0, out)
        missing = [sha[:7] for sha in shas if not self.names_verified(out, sha)]
        self.assertEqual(missing, [], "Verified gaps not listed, of %d commits:\n%s" % (len(shas), out))

    def test_empty_range_lists_nothing(self):
        """Empty state, a control green on the old code too: a range with no commits prints no sha."""
        self.base()
        rc, out = self.lint()
        self.assertEqual(rc, 0, out)
        self.assertEqual([line for line in out.splitlines() if re.search(r"\b[0-9a-f]{7,40}\b", line)], [], out)

    def test_repo_without_the_check_judges_no_verified_line(self):
        """A control, green on the old code too: a repo whose HEAD lacks the check file gets no Verified line, so child repos stay off."""
        self.base(check=False)
        sha = self.commit("change widget product", {PRODUCT_REL: PRODUCT_TEXT}, verified=None)
        rc, out = self.lint(script=MODULE, cwd=self.tree)
        self.assertEqual(rc, 0, out)
        self.assertNotListed(out, sha, "a repo whose HEAD lacks the check lists a Verified gap")

    def gap_rows(self, base):
        """The rows `gaps` returns for the fixture repo, the call the push guard makes (hooks/guard_merge.py)."""
        probe = ("import importlib.util, sys\n"
                 "spec = importlib.util.spec_from_file_location('check_red_run', sys.argv[1])\n"
                 "module = importlib.util.module_from_spec(spec)\n"
                 "spec.loader.exec_module(module)\n"
                 "for line in module.gaps(sys.argv[2], sys.argv[3]):\n"
                 "    print(line)\n")
        done = subprocess.run([sys.executable, "-c", probe, MODULE, self.tree, base],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", env=GIT_ENV)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout.splitlines()

    def test_push_guard_gaps_name_no_verified_line(self):
        """A control, green on the old code too: `gaps`, which the push guard calls in every repo, lists no Verified gap.
        Only main() reports a Verified gap, in observe mode."""
        self.base()
        self.commit("change widget product", {PRODUCT_REL: PRODUCT_TEXT}, verified=None)
        self.assertEqual(self.gap_rows(self.base_sha), [], "gaps() lists a Verified gap, which the push guard would read")

    def run_probe(self, watch, mode, args=None):
        """Run the check by MODULE path in the fixture repo, under PROBE. Returns (exit code, output, starts of `watch`).
        The probe's result lines must print, so a crash is never read as an exit code. Not the fixture's disk copy: a
        case that commits the check file without the marker overwrites that copy."""
        argv = ["--base", self.base_sha] if args is None else args
        done = subprocess.run([sys.executable, "-c", PROBE, MODULE, watch, mode, *argv], cwd=self.tree,
                              capture_output=True, text=True, encoding="utf-8", errors="replace", env=GIT_ENV)
        out = done.stdout + done.stderr
        exits = re.findall(r"^PROBE_EXIT=(\d+)$", out, re.M)
        starts = re.findall(r"^PROBE_STARTS=(\d+)$", out, re.M)
        self.assertTrue(exits and starts, "the probe printed no result, so it crashed:\n" + out)
        return int(exits[0]), out, int(starts[0])

    def test_unread_verified_read_exits_zero_with_one_observe_line(self):
        """A Verified read git cannot finish prints one OBSERVE line and exits 0, not the Unknown exit 2."""
        self.base()
        self.commit("change widget product", {PRODUCT_REL: PRODUCT_TEXT}, verified=None)  # the Verified read judges this commit
        rc, out, starts = self.run_probe("grep", "fail")
        self.assertGreaterEqual(starts, 1, "the simulated failure never reached the Verified read:\n" + out)  # scope before subject
        self.assertEqual(rc, 0, "observe mode: an unread Verified line must leave the exit code at 0:\n" + out)
        observe = [line for line in out.splitlines() if "OBSERVE" in line]
        self.assertEqual(len(observe), 1, "one OBSERVE line for the unread Verified read:\n" + out)
        self.assertIn("the Verified line read could not run", observe[0], out)

    def test_unread_verified_read_keeps_the_red_run_exit_one(self):
        """A Red-run gap keeps exit 1 when the Verified read cannot finish, and the OBSERVE line joins the FAIL line.
        The Verified read's Unknown does not raise that exit to 2."""
        self.base()
        self.commit("add widget tests", {self.new_test_path(): TEST_TEXT}, verified=None)  # no Red-run line: a Red-run gap
        rc, out, starts = self.run_probe("grep", "fail")
        self.assertGreaterEqual(starts, 1, "the simulated failure never reached the Verified read:\n" + out)  # scope before subject
        self.assertTrue(any("check_red_run: FAIL" in line for line in out.splitlines()), "the Red-run gap is not named:\n" + out)
        self.assertEqual(rc, 1, "a Red-run gap keeps the exit at 1 when the Verified read cannot run:\n" + out)
        observe = [line for line in out.splitlines() if "OBSERVE" in line]
        self.assertEqual(len(observe), 1, "one OBSERVE line for the unread Verified read:\n" + out)

    def test_unread_red_run_read_still_exits_two(self):
        """Control for the observe cases: a Red-run read git cannot finish still exits 2, as UNKNOWN."""
        self.base()
        self.commit("change widget product", {PRODUCT_REL: PRODUCT_TEXT}, verified=None)
        rc, out, starts = self.run_probe("log", "fail")
        self.assertGreaterEqual(starts, 1, "the simulated failure never reached the Red-run read:\n" + out)  # scope before subject
        self.assertEqual(rc, 2, "a Red-run read git cannot finish must exit 2:\n" + out)
        self.assertIn("check_red_run: UNKNOWN", out, out)

    def test_empty_range_starts_no_git_grep(self):
        """Empty state, a control. The Cost of decision verified-trailer (Verified line): an empty
        range starts no git grep."""
        self.base()
        rc, out, starts = self.run_probe("grep", "count")
        self.assertEqual(rc, 0, out)
        self.assertEqual(starts, 0, "an empty range starts %d git grep; the Cost says 0" % starts)

    def test_verified_read_starts_one_git_grep_and_one_per_unverified_commit(self):
        """Control. The Cost of decision verified-trailer: one git grep for HEAD, then one for the
        parent of each commit with no valid line that is not a revert. Three such commits, one verified commit and its
        revert: 1 + 3."""
        self.base()
        for i in range(3):
            self.commit("change part %d" % i, {"src/part_%d.py" % i: "def part():\n    return %d\n" % i}, verified=None)
        self.commit("change part 3", {"src/part_3.py": "def part():\n    return 3\n"})  # a valid line: no git grep
        self.git("revert", "--no-edit", "HEAD")  # a revert: not judged, so no git grep
        rc, out, starts = self.run_probe("grep", "count")
        self.assertEqual(rc, 0, out)
        self.assertEqual(starts, 1 + 3, "the Verified read starts %d git grep; the Cost says 1 + 3" % starts)

    def test_full_size_range_starts_one_git_grep_per_commit_plus_one(self):
        """Full-size state, a control: 25 unverified commits start 1 + 25 git grep."""
        self.base()
        for i in range(25):
            self.commit("change part %d" % i, {"src/part_%d.py" % i: "def part():\n    return %d\n" % i}, verified=None)
        rc, out, starts = self.run_probe("grep", "count")
        self.assertEqual(rc, 0, out)
        self.assertEqual(starts, 1 + 25, "the Verified read starts %d git grep; the Cost says 1 + 25" % starts)

    def test_head_without_the_marker_starts_one_git_grep(self):
        """Control. The Cost of decision verified-trailer: a HEAD without the marker starts one git grep."""
        self.base()
        self.commit("change widget product", {PRODUCT_REL: PRODUCT_TEXT}, verified=None)
        dropped = self.commit("drop the Verified rollout", {CHECK_REL: PRE_ROLLOUT_CHECK}, verified=None)
        self.assertNotIn(ROLLOUT_MARKER, self.git("show", dropped + ":" + CHECK_REL), "fixture: HEAD still holds the marker")
        rc, out, starts = self.run_probe("grep", "count")
        self.assertEqual(rc, 0, out)
        self.assertEqual(starts, 1, "a HEAD without the marker starts %d git grep; the Cost says 1" % starts)

    def test_head_without_the_marker_judges_nothing_over_a_parent_that_has_it(self):
        """HEAD lacks the marker and its parent holds it: no commit is judged. The control is the same range with HEAD
        holding the marker, which lists both commits. Red on a check that drops the HEAD gate."""
        self.base()
        self.git("checkout", "-q", "-b", "keep")
        held = self.commit("change widget product", {PRODUCT_REL: PRODUCT_TEXT}, verified=None)  # its parent holds the marker
        kept = self.commit("change gadget product", {GADGET_PATH: GADGET_TEXT}, verified=None)  # HEAD holds the marker
        rc, out, _starts = self.run_probe("grep", "count")
        self.assertEqual(rc, 0, out)
        self.assertListed(out, held, "change widget product")  # control: with the marker at HEAD, the parent's commit is judged
        self.assertListed(out, kept, "change gadget product")
        self.git("checkout", "-q", "-b", "drop", held)
        dropped = self.commit("drop the Verified rollout", {CHECK_REL: PRE_ROLLOUT_CHECK}, verified=None)  # HEAD lacks the marker
        self.assertNotIn(ROLLOUT_MARKER, self.git("show", dropped + ":" + CHECK_REL), "fixture: HEAD still holds the marker")
        self.assertIn(ROLLOUT_MARKER, self.git("show", held + ":" + CHECK_REL), "fixture: the parent lost the marker")
        rc, out, _starts = self.run_probe("grep", "count")
        self.assertEqual(rc, 0, out)
        self.assertNotListed(out, dropped, "a HEAD without the marker is judged over a parent that holds it")
        self.assertNotListed(out, held, "a commit is judged when HEAD lacks the marker")

    def test_root_commit_is_not_judged_and_its_child_is_listed(self):
        """A root commit has no parent, so it is not judged. The commit on it is judged: the root holds the marker.
        The child's listing is the control: an empty listing cannot pass the root check."""
        self.base()
        self.git("checkout", "-q", "--orphan", "new-history")
        self.git("rm", "-r", "-q", "--cached", "--", ".")  # the root commit holds only the check file, which it names
        root = self.commit("start a new history", {CHECK_REL: read_module()}, verified=None)
        self.assertEqual(self.git("log", "-1", "--format=%P", root), "", "fixture: the root commit has a parent")  # scope
        child = self.commit("change widget product", {PRODUCT_REL: PRODUCT_TEXT}, verified=None)
        rc, out, _starts = self.run_probe("grep", "count")
        self.assertEqual(rc, 0, out)
        self.assertListed(out, child, "change widget product")
        self.assertNotListed(out, root, "a root commit is judged, so it is listed as a Verified gap")


if __name__ == "__main__":
    unittest.main()
