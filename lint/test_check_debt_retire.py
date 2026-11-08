#!/usr/bin/env python3
"""Fixture suite for lint/check_debt_retire.py. Run: python3 lint/test_check_debt_retire.py

Every case builds a throwaway git repo in its own folder under this run's temp root (decision test-temp-standard),
commits a base and a head, and asks the check for its findings. A fixture test script appends its own name and its
working folder to the file named by RETIRE_MARKS, so a case shows that a Retire check ran, or did not, from that file.
No case waits on a clock. The Retire-run cases pass a fake run_state, so no case reads the network.
"""
import atexit, inspect, json, os, shutil, subprocess, sys, tempfile, unittest, unittest.mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: the run folder's one home (lint/_test_temp.py)
import check_debt_retire as D  # noqa: E402  the module under test
import layout  # noqa: E402  the one layout: where the debts folder is (lint/layout.py)

RUN = os.path.realpath(_test_temp.run_folder())
atexit.register(shutil.rmtree, RUN, True)
os.environ.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                  GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")

# A fixture test script: it leaves a mark (its name and its working folder) and exits with the code given.
MARKED = ("import os, sys\n"
          "with open(os.environ['RETIRE_MARKS'], 'a', encoding='utf-8') as f:\n"
          "    f.write(os.path.basename(__file__) + ' ' + os.getcwd() + '\\n')\n"
          "sys.exit(%d)\n")
EXTRAS = {"kinds": {}, "rolled-out": True}  # a rolled-out repo keeps debts at docs/debts
BASE = {
    ".claude/layout-extras.json": json.dumps(EXTRAS) + "\n",
    "docs/debts/README.md": "# Debts\n\n- **Retire.** Run `tests/test_fail.py`.\n",  # a README is not a debt, even with a Retire line
    "docs/debts/notes.md": "# Notes\n\n- **Retire.** Run `tests/test_fail.py`.\n",
    "tests/test_pass.py": MARKED % 0,
    "tests/test_fail.py": MARKED % 1,
    "tests/test_pass.mjs": "export {};\n",
}
WHAT = "A finding the Retire check closes, written out in full so that a rename keeps most of this text. " * 2
PASS = "Delete the old helper. Check: `tests/test_pass.py`."
FAIL = "Delete the old helper. Check: `tests/test_fail.py`."
PROSE = "Delete the old helper once nothing reads it."
RUN_URL = "https://github.com/fixture/repo/actions/runs/42"
ATTRIBUTION = "\U0001F916 Generated with [Claude Code](https://claude.com/claude-code)"
NO_RETIRED = "check_debt_retire has no retired(): a Retire-run cite cannot excuse a debt close (decision debt-close-runs-retire)"
HEAD_URL = "https://github.com/fixture/repo/actions/runs/77"  # the PR head's own checks run
NO_HEAD_RUN = "check() takes no head_run: the merge-mode read of the head's own checks run is not built (ruling 20:03 CST)"


def sh(cwd, *cmd):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    assert r.returncode == 0, (cmd, r.stdout, r.stderr)
    return r.stdout.strip()


def put(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def debt(retire):
    return "# A debt\n\n- **What.** %s\n- **Where.** None.\n- **Decision.** none\n- **Retire.** %s\n" % (WHAT, retire)


def pairs(findings):
    return sorted((f.slug, f.kind) for f in findings)


class Runs:
    """A fake run_state: each call records its URL, then answers with the pair given, or raises the error given."""

    def __init__(self, answer):
        self.answer, self.urls = answer, []

    def __call__(self, url):
        self.urls.append(url)
        if isinstance(self.answer, BaseException):
            raise self.answer
        return self.answer


class HeadRuns:
    """A fake head_run: answers the head's own checks run as (conclusion, url), or None when the head has no run. A conclusion of
    None is a run still pending. Each call records the head sha it was asked about."""

    def __init__(self, answer):
        self.answer, self.shas = answer, []

    def __call__(self, sha):
        self.shas.append(sha)
        return self.answer


class Case(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="case-", dir=RUN)
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.marks = os.path.join(self.folder, "marks.txt")
        patch = unittest.mock.patch.dict(os.environ, {"RETIRE_MARKS": self.marks})
        patch.start()
        self.addCleanup(patch.stop)
        self.dir = self.base = self.head = None

    def repo(self, debts=None, folder="docs/debts", extras=None, rolled=True):
        """A repo whose base commit holds BASE, the debts ({name: Retire text}) in `folder`, and `extras` as its layout file.
        `rolled=False` drops the layout file, so the repo keeps its debts where the legacy map puts them."""
        self.dir = tempfile.mkdtemp(prefix="repo-", dir=self.folder)
        sh(self.dir, "git", "init", "-q", "-b", "main")
        files = dict(BASE)
        if not rolled:
            del files[".claude/layout-extras.json"]
        for name, retire in (debts or {}).items():
            files["%s/%s.md" % (folder, name)] = debt(retire)
        if extras is not None:
            files[".claude/layout-extras.json"] = json.dumps(extras) + "\n"
        for path, text in files.items():
            put(os.path.join(self.dir, path), text)
        sh(self.dir, "git", "add", "-A")
        sh(self.dir, "git", "commit", "-q", "-m", "base")
        self.base = self.head = sh(self.dir, "git", "rev-parse", "HEAD")

    def change(self, write=None, rm=(), mv=()):
        """Commit a head on the base: `write` ({path: text}), `rm` (paths), and `mv` ((from, to) pairs)."""
        for path, text in (write or {}).items():
            put(os.path.join(self.dir, path), text)
        for path in rm:
            sh(self.dir, "git", "rm", "-q", path)
        for src, dst in mv:
            os.makedirs(os.path.dirname(os.path.join(self.dir, dst)), exist_ok=True)
            sh(self.dir, "git", "mv", src, dst)
        sh(self.dir, "git", "add", "-A")
        sh(self.dir, "git", "commit", "-q", "-m", "head")
        self.head = sh(self.dir, "git", "rev-parse", "HEAD")

    def findings(self, head=None, pr_body="", run_state=None):
        return D.check(self.dir, self.base, head=head or self.head, pr_body=pr_body, run_state=run_state)

    def ran(self):
        """(script name, working folder) for each fixture script that ran, in the order it ran."""
        try:
            with open(self.marks, encoding="utf-8") as f:
                return [tuple(line.split(" ", 1)) for line in f.read().splitlines()]
        except FileNotFoundError:
            return []

    def layout_elsewhere(self):
        """The layout as a repo whose origin is fixture/elsewhere sees it: legacy-repos keeps its debts in records/debts."""
        patch = unittest.mock.patch.multiple(layout, repo_name=lambda root: "fixture/elsewhere",
                                             legacy_repos=lambda: {"fixture/elsewhere": {"debts": "records/debts"}})
        patch.start()
        self.addCleanup(patch.stop)

    def cli(self):
        return subprocess.run([sys.executable, os.path.join(HERE, "check_debt_retire.py"), "--upstream", self.base, "--head", self.head],
                              cwd=self.dir, capture_output=True, text=True)

    def no_node(self):
        """PATH holds git and python3 alone: node is not found, so a .mjs check cannot run, and a .py check still can."""
        bindir = os.path.join(self.folder, "bin")
        os.makedirs(bindir, exist_ok=True)
        for tool in ("git", "python3"):
            os.symlink(shutil.which(tool), os.path.join(bindir, tool))
        patch = unittest.mock.patch.dict(os.environ, {"PATH": bindir})
        patch.start()
        self.addCleanup(patch.stop)

    def statuses(self):
        """The git status letter of each path from base to head, with rename detection on, as git pairs them."""
        return [line.split("\t")[0][0] for line in sh(self.dir, "git", "diff", "--name-status", "-M", self.base, self.head).splitlines()]


class Closes(Case):
    """A debt file deleted between base and head is a close, and its Retire check runs on the head."""

    def test_1_a_deleted_debt_whose_retire_names_a_passing_test_runs_it_and_passes(self):
        self.repo(debts={"d-pass": PASS})
        self.change(rm=["docs/debts/d-pass.md"])
        found = self.findings()
        self.assertEqual(self.ran(), [("test_pass.py", self.dir)], "the close's Retire check did not run in the head folder")
        self.assertEqual(pairs(found), [], "a passing Retire check gave a finding")

    def test_2_a_deleted_debt_whose_retire_names_a_failing_test_is_red(self):
        self.repo(debts={"d-fail": FAIL})
        self.change(rm=["docs/debts/d-fail.md"])
        found = self.findings()
        self.assertEqual(self.ran(), [("test_fail.py", self.dir)], "the failing Retire check did not run in the head folder")
        self.assertEqual(pairs(found), [("d-fail", "red")], "a failing Retire check gave no red finding")

    def test_3_a_retire_check_whose_interpreter_is_not_on_path_is_unknown_not_red(self):
        self.repo(debts={"d-mjs": "Delete the old helper. Check: `tests/test_pass.mjs`."})
        self.no_node()
        self.change(rm=["docs/debts/d-mjs.md"])
        self.assertEqual(pairs(self.findings()), [("d-mjs", "unknown")], "a missing interpreter did not read as unknown")

    def test_13_a_span_that_cannot_run_is_unknown_even_before_a_passing_span(self):
        self.repo(debts={"d-two": "Delete the old helper. Check: `tests/test_pass.mjs` then `tests/test_pass.py`."})
        self.no_node()
        self.change(rm=["docs/debts/d-two.md"])
        found = self.findings()
        self.assertEqual(self.ran(), [("test_pass.py", self.dir)], "the passing span after the unrunnable one did not run")
        self.assertEqual(pairs(found), [("d-two", "unknown")], "a later passing span hid the unknown of an earlier span")

    def test_13b_a_span_that_cannot_run_after_a_passing_span_is_unknown(self):
        self.repo(debts={"d-two": "Delete the old helper. Check: `tests/test_pass.py` then `tests/test_pass.mjs`."})
        self.no_node()
        self.change(rm=["docs/debts/d-two.md"])
        found = self.findings()
        self.assertEqual(self.ran(), [("test_pass.py", self.dir)], "the passing span before the unrunnable one did not run")
        self.assertEqual(pairs(found), [("d-two", "unknown")], "an unrunnable span after a passing one did not read as unknown")

    def test_4_a_prose_only_retire_is_prose_and_holds_the_retire_text(self):
        self.repo(debts={"d-prose": PROSE})
        self.change(rm=["docs/debts/d-prose.md"])
        found = self.findings()
        self.assertEqual(self.ran(), [], "a prose Retire ran a script")
        self.assertEqual(pairs(found), [("d-prose", "prose")], "a prose Retire gave no prose finding")
        self.assertIn(PROSE, found[0].text, "the prose finding does not hold the Retire text it read")

    def test_4b_a_retire_naming_a_path_that_is_not_a_test_is_prose(self):
        self.repo(debts={"d-config": "Delete the old helper. Check: `.claude/layout-extras.json`."})
        self.change(rm=["docs/debts/d-config.md"])
        found = self.findings()
        self.assertEqual(self.ran(), [], "a non-test path ran")
        self.assertEqual(pairs(found), [("d-config", "prose")])

    def test_4c_a_retire_naming_a_test_the_pr_deletes_is_prose(self):
        self.repo(debts={"d-gone": PASS})
        self.change(rm=["docs/debts/d-gone.md", "tests/test_pass.py"])
        found = self.findings()
        self.assertEqual(self.ran(), [], "a test the head no longer tracks ran")
        self.assertEqual(pairs(found), [("d-gone", "prose")])

    def test_4d_a_lone_backtick_in_retire_prose_does_not_swallow_the_real_span(self):
        self.repo(debts={"d-tick": "Mind the lone ` mark. Check: `tests/test_pass.py`."})
        self.change(rm=["docs/debts/d-tick.md"])
        found = self.findings()
        self.assertEqual(self.ran(), [("test_pass.py", self.dir)], "the real span after a lone backtick did not run")
        self.assertEqual(pairs(found), [], "a lone backtick made the Retire read as prose")

    def test_5_a_rename_inside_the_debts_folder_runs_nothing(self):
        self.repo(debts={"d-fail": FAIL})
        self.change(mv=[("docs/debts/d-fail.md", "docs/debts/d-fail-renamed.md")])
        found = self.findings()
        self.assertEqual(self.ran(), [], "a rename inside the folder ran a Retire check")
        self.assertEqual(pairs(found), [])

    def test_6_a_rename_out_of_the_debts_folder_runs_the_check(self):
        self.repo(debts={"d-fail": FAIL})
        self.change(mv=[("docs/debts/d-fail.md", "docs/archive/d-fail.md")])
        found = self.findings()
        self.assertEqual(self.ran(), [("test_fail.py", self.dir)], "a rename out of the folder did not run its Retire check")
        self.assertEqual(pairs(found), [("d-fail", "red")])

    def test_6b_a_rename_out_reads_the_retire_text_of_the_base(self):
        self.repo(debts={"d-fail": FAIL})
        self.change(write={"docs/archive/d-fail.md": debt(PASS)}, rm=["docs/debts/d-fail.md"])  # the head rewrites Retire to a passing test
        found = self.findings()
        self.assertEqual(self.ran(), [("test_fail.py", self.dir)], "the head's Retire text ran, not the base's")
        self.assertEqual(pairs(found), [("d-fail", "red")])

    def test_7_two_debts_deleted_in_one_diff_both_run_and_one_red_is_enough(self):
        self.repo(debts={"d-ok": PASS, "d-bad": FAIL})
        self.change(rm=["docs/debts/d-ok.md", "docs/debts/d-bad.md"])
        found = self.findings()
        self.assertEqual(sorted(self.ran()), [("test_fail.py", self.dir), ("test_pass.py", self.dir)], "not both Retire checks ran")
        self.assertEqual(pairs(found), [("d-bad", "red")])

    def test_8a_the_debts_folder_is_the_one_the_layout_names(self):
        self.layout_elsewhere()
        self.repo(debts={"d-fail": FAIL}, folder="records/debts", extras={"kinds": {"debts": {"path": "records/debts"}}, "rolled-out": True})
        self.change(rm=["records/debts/d-fail.md"])
        found = self.findings()
        self.assertEqual(self.ran(), [("test_fail.py", self.dir)], "a debt in the layout's debts folder did not run its check")
        self.assertEqual(pairs(found), [("d-fail", "red")])

    def test_8b_the_default_debts_folder_is_not_read_where_the_layout_moves_it(self):
        self.layout_elsewhere()
        self.repo(debts={"decoy": FAIL}, folder="docs/debts", extras={"kinds": {"debts": {"path": "records/debts"}}, "rolled-out": True})
        self.change(rm=["docs/debts/decoy.md"])
        found = self.findings()
        self.assertEqual(self.ran(), [], "a file in the default folder ran a check though the layout moves debts")
        self.assertEqual(pairs(found), [])

    def test_9_readme_and_notes_are_not_debts(self):
        self.repo()
        self.change(rm=["docs/debts/README.md", "docs/debts/notes.md"])
        found = self.findings()
        self.assertEqual(self.ran(), [], "deleting README or notes ran a Retire check")
        self.assertEqual(pairs(found), [])

    def test_10_the_cli_exits_1_on_a_finding_and_0_otherwise(self):
        self.repo(debts={"d-fail": FAIL})
        self.change(rm=["docs/debts/d-fail.md"])
        red = self.cli()
        self.assertEqual(red.returncode, 1, "CLI on a red close: " + red.stdout + red.stderr)
        self.assertIn("d-fail", red.stdout, "the CLI does not name the debt it refused")
        self.repo(debts={"d-pass": PASS})
        self.change(rm=["docs/debts/d-pass.md"])
        green = self.cli()
        self.assertEqual(green.returncode, 0, "CLI on a green close: " + green.stdout + green.stderr)

    def test_11_a_pr_that_closes_no_debt_has_no_finding_and_runs_nothing(self):
        self.repo(debts={"d-fail": FAIL})
        self.change(write={"tests/test_pass.py": MARKED % 0 + "# touched\n"})
        found = self.findings()
        self.assertEqual(self.ran(), [], "a PR with no debt change ran a check")
        self.assertEqual(pairs(found), [])

    def test_12_a_debt_edited_in_place_is_not_a_close(self):
        self.repo(debts={"d-fail": FAIL})
        self.change(write={"docs/debts/d-fail.md": debt(PASS)})
        found = self.findings()
        self.assertEqual(self.ran(), [], "an edited debt ran a Retire check")
        self.assertEqual(pairs(found), [])

    def test_14_a_rename_in_the_folder_whose_retire_changed_is_a_close_that_runs_the_base_retire(self):
        self.repo(debts={"d-fail": FAIL})
        self.change(write={"docs/debts/d-fail-b.md": debt(PASS)}, rm=["docs/debts/d-fail.md"])
        self.assertEqual(self.statuses(), ["R"], "git did not pair the new debt with the old one, so the case proves nothing")
        found = self.findings()
        self.assertEqual(self.ran(), [("test_fail.py", self.dir)], "the base Retire did not run for a debt whose Retire changed")
        self.assertEqual(pairs(found), [("d-fail", "red")], "a close by rename with a changed Retire gave no red finding")

    def test_15_a_repo_without_rolled_out_extras_is_read_at_docs_debts(self):
        self.repo(debts={"d-fail": FAIL}, rolled=False)
        self.change(rm=["docs/debts/d-fail.md"])
        found = self.findings()
        self.assertEqual(self.ran(), [("test_fail.py", self.dir)], "a debt at docs/debts in an unrolled repo did not run its check")
        self.assertEqual(pairs(found), [("d-fail", "red")])

    def test_16_the_retire_text_is_read_at_the_base_tip_not_the_fork_point(self):
        self.repo(debts={"d-moved": PROSE})  # the fork point: the debt names no runnable check
        sh(self.dir, "git", "checkout", "-q", "-b", "pr")
        self.change(rm=["docs/debts/d-moved.md"])  # the PR closes the debt
        pr = self.head
        sh(self.dir, "git", "checkout", "-q", "main")
        put(os.path.join(self.dir, "docs/debts/d-moved.md"), debt(FAIL))  # the base edits the Retire after the fork
        sh(self.dir, "git", "add", "-A")
        sh(self.dir, "git", "commit", "-q", "-m", "base: the Retire names a test")
        self.base = sh(self.dir, "git", "rev-parse", "HEAD")
        sh(self.dir, "git", "checkout", "-q", "pr")
        self.head = pr
        found = self.findings()
        self.assertEqual(self.ran(), [("test_fail.py", self.dir)], "the Retire of the base tip did not run")
        self.assertEqual(pairs(found), [("d-moved", "red")], "the Retire of the fork point was read, not the base tip's")


class RetireRun(Case):
    """A debt closes with a `Retire-run: <slug> -- <run URL>` line in the PR body. The cited run must be green and on the PR
    head or a commit on top of it. A prose Retire is the case it exists for."""

    def closed_prose(self):
        self.repo(debts={"d-prose": PROSE})
        self.change(rm=["docs/debts/d-prose.md"])

    def test_r1_an_accepted_cite_clears_a_prose_debt_when_its_run_is_green_on_the_head(self):
        self.closed_prose()
        runs = Runs(("success", self.head))
        body = "Summary.\n\nRetire-run: d-prose -- %s\n\n%s" % (RUN_URL, ATTRIBUTION)
        found = self.findings(pr_body=body, run_state=runs)
        self.assertEqual(runs.urls, [RUN_URL], "the cited run was not read")
        self.assertEqual(pairs(found), [], "a green run on the PR head did not clear the prose debt")

    def test_r1b_a_green_run_on_a_commit_above_the_head_clears_the_prose_debt(self):
        self.closed_prose()
        pr_head = self.head
        self.change(write={"notes/after.txt": "later\n"})  # the run's commit: one on top of the PR head
        runs = Runs(("success", self.head))
        found = self.findings(head=pr_head, pr_body="Retire-run: d-prose -- %s\n" % RUN_URL, run_state=runs)
        self.assertEqual(runs.urls, [RUN_URL], "the cited run was not read")
        self.assertEqual(pairs(found), [], "a green run on a descendant of the PR head did not clear the debt")

    def test_r2_a_cite_of_a_failing_run_is_red(self):
        self.closed_prose()
        runs = Runs(("failure", self.head))
        found = self.findings(pr_body="Retire-run: d-prose -- %s\n" % RUN_URL, run_state=runs)
        self.assertEqual(pairs(found), [("d-prose", "red")], "a failing cited run did not refuse as red")

    def merge_mode(self, pr_body, run_state, head_run):
        """check() in merge mode, as debt_check calls it: a deferred cite is held on the head's own checks run, read through head_run.
        A check() with no head_run parameter fails the case by name."""
        self.assertIn("head_run", inspect.signature(D.check).parameters, NO_HEAD_RUN)
        return D.check(self.dir, self.base, head=self.head, pr_body=pr_body, run_state=run_state, head_run=head_run)

    def sibling_sha(self):
        """A commit on a branch cut from the base that the PR head does not contain. -> its sha. The checkout is back on main."""
        sh(self.dir, "git", "checkout", "-q", "-b", "side", self.base)
        put(os.path.join(self.dir, "side.txt"), "side\n")
        sh(self.dir, "git", "add", "-A")
        sh(self.dir, "git", "commit", "-q", "-m", "side")
        side = sh(self.dir, "git", "rev-parse", "HEAD")
        sh(self.dir, "git", "checkout", "-q", "main")
        return side

    def closed_prose_on_a_lane(self):
        """The debt closed on a head that holds a lane tip: a commit cut from the base and merged into the head, so the tip is in base..head.
        -> the lane tip's sha. self.head is the PR head."""
        self.repo(debts={"d-prose": PROSE})
        lane = self.sibling_sha()
        sh(self.dir, "git", "merge", "-q", "--no-ff", "-m", "merge the lane", "side")
        self.change(rm=["docs/debts/d-prose.md"])
        return lane

    def test_d1_a_deferred_cite_with_a_green_head_run_is_no_finding(self):
        # Ruling 20:34 CST: a cited sha in base..head (a lane tip) is deferred to merge, and merge mode holds it on the head's run.
        lane = self.closed_prose_on_a_lane()
        head_runs = HeadRuns(("success", HEAD_URL))
        found = self.merge_mode("Retire-run: d-prose -- %s\n" % RUN_URL, Runs(("success", lane)), head_runs)
        self.assertEqual(head_runs.shas, [self.head], "the head's own checks run was not read")
        self.assertEqual(pairs(found), [], "a deferred cite with a green head run did not clear the debt")

    def test_d2_a_deferred_cite_with_a_red_head_run_is_a_finding_that_names_the_head_run(self):
        lane = self.closed_prose_on_a_lane()
        found = self.merge_mode("Retire-run: d-prose -- %s\n" % RUN_URL, Runs(("success", lane)), HeadRuns(("failure", HEAD_URL)))
        self.assertEqual([f.slug for f in found], ["d-prose"], "a deferred cite with a red head run did not refuse")
        self.assertIn(HEAD_URL, found[0].text, "the refusal does not name the head's checks run")

    def test_r3_a_green_run_on_an_older_commit_is_deferred_and_a_missing_head_run_refuses(self):
        # Ruling 20:34 CST: the lane tip is in base..head, so the cite is deferred, not red. With no head run it refuses.
        lane = self.closed_prose_on_a_lane()
        head_runs = HeadRuns(None)  # the PR head has no checks run
        found = self.merge_mode("Retire-run: d-prose -- %s\n" % RUN_URL, Runs(("success", lane)), head_runs)
        self.assertEqual(head_runs.shas, [self.head], "the head's own checks run was not read")
        self.assertEqual([f.slug for f in found], ["d-prose"], "a deferred cite with no head run cleared the debt")

    def test_d4_a_deferred_cite_with_a_pending_head_run_is_a_finding_that_names_the_head_run(self):
        lane = self.closed_prose_on_a_lane()
        found = self.merge_mode("Retire-run: d-prose -- %s\n" % RUN_URL, Runs(("success", lane)), HeadRuns((None, HEAD_URL)))
        self.assertEqual([f.slug for f in found], ["d-prose"], "a deferred cite with a pending head run did not refuse")
        self.assertIn(HEAD_URL, found[0].text, "the refusal does not name the pending head run")

    def test_d5_a_cite_of_a_sha_the_head_does_not_contain_stays_red(self):  # control
        self.closed_prose()
        side = self.sibling_sha()
        found = self.findings(pr_body="Retire-run: d-prose -- %s\n" % RUN_URL, run_state=Runs(("success", side)))
        self.assertEqual(pairs(found), [("d-prose", "red")], "a green run on a commit the head does not contain did not stay red")

    def test_r14_a_green_run_on_an_old_main_commit_is_red_and_not_deferred(self):
        # Ruling 20:34 CST: only a cited sha the branch holds (in base..head) is deferred. An ancestor of the base is judged as today.
        self.repo(debts={"d-prose": PROSE})
        old = self.base  # a main commit that the base and the head both hold
        self.change(write={"notes/main.txt": "main\n"})
        self.base = self.head  # the base the PR was cut from: main's tip, one commit on
        self.change(rm=["docs/debts/d-prose.md"])
        body = "Retire-run: d-prose -- %s\n" % RUN_URL
        with self.subTest(mode="CI mode (defer)"):
            found = D.check(self.dir, self.base, head=self.head, pr_body=body, run_state=Runs(("success", old)), defer=True)
            self.assertEqual(pairs(found), [("d-prose", "red")], "a green run on an old main commit was deferred in CI mode, not judged red")
            self.assertIn("not on the PR head", found[0].text, "the refusal does not give the cause: not on the PR head")
        with self.subTest(mode="merge mode (head_run)"):
            heads = HeadRuns(("success", HEAD_URL))
            found = D.check(self.dir, self.base, head=self.head, pr_body=body, run_state=Runs(("success", old)), head_run=heads)
            self.assertEqual(pairs(found), [("d-prose", "red")], "a green run on an old main commit was deferred in merge mode, not judged red")
            self.assertEqual(heads.shas, [], "merge mode read the head's checks run for a cite that is not in base..head")

    def test_r15_a_lane_tip_in_base_to_head_still_defers(self):  # control
        self.repo(debts={"d-prose": PROSE})
        lane = self.sibling_sha()  # the lane's commit, cut from the base
        sh(self.dir, "git", "merge", "-q", "--no-ff", "-m", "merge the lane", "side")  # the batch takes the lane in: it is in base..head
        self.change(rm=["docs/debts/d-prose.md"])
        body = "Retire-run: d-prose -- %s\n" % RUN_URL
        with self.subTest(mode="CI mode (defer)"):
            found = D.check(self.dir, self.base, head=self.head, pr_body=body, run_state=Runs(("success", lane)), defer=True)
            self.assertEqual(pairs(found), [], "a lane tip in base..head was not deferred in CI mode")
        with self.subTest(mode="merge mode (head_run)"):
            heads = HeadRuns(("success", HEAD_URL))
            found = D.check(self.dir, self.base, head=self.head, pr_body=body, run_state=Runs(("success", lane)), head_run=heads)
            self.assertEqual(pairs(found), [], "a lane tip in base..head with a green head run was refused in merge mode")
            self.assertEqual(heads.shas, [self.head], "merge mode did not read the head's checks run for a lane tip in base..head")

    def test_r16_a_green_run_on_the_base_tip_is_red_and_not_deferred(self):
        # Ruling 20:34 CST: the base tip is a main commit, not a lane tip. A cite on it is judged as today: red, never deferred.
        self.repo(debts={"d-prose": PROSE})
        self.change(rm=["docs/debts/d-prose.md"])  # the head removes the debt on top of the base tip
        body = "Retire-run: d-prose -- %s\n" % RUN_URL
        with self.subTest(mode="CI mode (defer)"):
            found = D.check(self.dir, self.base, head=self.head, pr_body=body, run_state=Runs(("success", self.base)), defer=True)
            self.assertEqual(pairs(found), [("d-prose", "red")], "a green run on the base tip was deferred in CI mode, not judged red")
            self.assertIn("not on the PR head", found[0].text, "the refusal does not give the cause: not on the PR head")
        with self.subTest(mode="merge mode (head_run)"):
            heads = HeadRuns(("success", HEAD_URL))
            found = D.check(self.dir, self.base, head=self.head, pr_body=body, run_state=Runs(("success", self.base)), head_run=heads)
            self.assertEqual(pairs(found), [("d-prose", "red")], "a green run on the base tip was deferred in merge mode, not judged red")
            self.assertEqual(heads.shas, [], "merge mode read the head's checks run for a cite on the base tip")

    def test_r4_an_unreadable_cited_run_is_unknown(self):
        self.closed_prose()
        runs = Runs(RuntimeError("the run read failed: HTTP 502"))
        found = self.findings(pr_body="Retire-run: d-prose -- %s\n" % RUN_URL, run_state=runs)
        self.assertEqual(pairs(found), [("d-prose", "unknown")], "an unreadable cited run did not read as unknown")

    def test_r5_a_cite_inside_a_code_fence_is_ignored(self):
        self.closed_prose()
        runs = Runs(("success", self.head))
        body = "Summary.\n\n```\nRetire-run: d-prose -- %s\n```\n" % RUN_URL
        found = self.findings(pr_body=body, run_state=runs)
        self.assertEqual(runs.urls, [], "a cite inside a code fence was read")
        self.assertEqual(pairs(found), [("d-prose", "prose")], "a fenced cite cleared the prose debt")

    def test_r6_a_cite_inside_an_html_comment_is_ignored(self):
        self.closed_prose()
        runs = Runs(("success", self.head))
        found = self.findings(pr_body="Summary.\n\n<!-- Retire-run: d-prose -- %s -->\n" % RUN_URL, run_state=runs)
        self.assertEqual(runs.urls, [], "a cite inside an HTML comment was read")
        self.assertEqual(pairs(found), [("d-prose", "prose")], "a commented-out cite cleared the prose debt")

    def test_r7_the_cite_key_is_case_insensitive(self):
        self.closed_prose()
        runs = Runs(("success", self.head))
        found = self.findings(pr_body="Summary.\n\nretire-run: d-prose -- %s\n" % RUN_URL, run_state=runs)
        self.assertEqual(runs.urls, [RUN_URL], "a lower-case Retire-run key was not read")
        self.assertEqual(pairs(found), [], "a lower-case Retire-run key did not clear the prose debt")

    def test_r8_a_green_cited_run_clears_a_check_the_machine_cannot_run(self):
        self.repo(debts={"d-mjs": "Delete the old helper. Check: `tests/test_pass.mjs`."})
        self.no_node()
        self.change(rm=["docs/debts/d-mjs.md"])
        runs = Runs(("success", self.head))
        found = self.findings(pr_body="Retire-run: d-mjs -- %s\n" % RUN_URL, run_state=runs)
        self.assertEqual(runs.urls, [RUN_URL], "the cited run was not read")
        self.assertEqual(pairs(found), [], "a green cited run did not clear a check the machine cannot run")

    def test_r9_a_green_cited_run_does_not_clear_a_red_check(self):
        self.repo(debts={"d-fail": FAIL})
        self.change(rm=["docs/debts/d-fail.md"])
        runs = Runs(("success", self.head))
        found = self.findings(pr_body="Retire-run: d-fail -- %s\n" % RUN_URL, run_state=runs)
        self.assertEqual(self.ran(), [("test_fail.py", self.dir)], "the red check did not run in the head folder")
        self.assertEqual(pairs(found), [("d-fail", "red")], "a green cited run cleared a red check")

    def retired_of(self, body, run_state):
        """retired() for this case's PR. A missing function is a named red: no close can be excused without it."""
        self.assertTrue(hasattr(D, "retired"), NO_RETIRED)
        return D.retired(self.dir, self.base, head=self.head, pr_body=body, run_state=run_state)

    def test_r10_retired_returns_the_debt_path_for_a_green_cite_on_a_prose_retire(self):
        self.closed_prose()
        body = "Summary.\n\nRetire-run: d-prose -- %s\n" % RUN_URL
        self.assertEqual(self.findings(pr_body=body, run_state=Runs(("success", self.head))), [], "scope: the debt-close check clears it")
        runs = Runs(("success", self.head))
        self.assertEqual(set(self.retired_of(body, runs)), {"docs/debts/d-prose.md"}, "retired() does not name the closed debt")
        self.assertEqual(runs.urls, [RUN_URL], "the cited run was not read")

    def test_r11_retired_returns_nothing_for_a_red_runnable_retire_with_a_green_cite(self):
        self.repo(debts={"d-fail": FAIL})
        self.change(rm=["docs/debts/d-fail.md"])
        body = "Retire-run: d-fail -- %s\n" % RUN_URL
        self.assertEqual(pairs(self.findings(pr_body=body, run_state=Runs(("success", self.head)))), [("d-fail", "red")], "scope")
        self.assertEqual(self.retired_of(body, Runs(("success", self.head))), {})

    def test_r12_retired_returns_nothing_for_an_uncited_close(self):
        self.closed_prose()
        runs = Runs(("success", self.head))
        self.assertEqual(pairs(self.findings(run_state=runs)), [("d-prose", "prose")], "scope")
        self.assertEqual(self.retired_of("Summary.\n", runs), {})
        self.assertEqual(runs.urls, [], "a run was read with no cite")

    def test_r13_retired_returns_nothing_without_a_run_reader(self):
        self.closed_prose()
        body = "Retire-run: d-prose -- %s\n" % RUN_URL
        self.assertEqual(pairs(self.findings(pr_body=body)), [("d-prose", "unknown")], "scope")
        self.assertEqual(self.retired_of(body, None), {})


if __name__ == "__main__":
    unittest.main()
