#!/usr/bin/env python3
"""Fixture suite for lint/check_debt_retire.py. Run: python3 lint/test_check_debt_retire.py

Every case builds a throwaway git repo in its own folder under this run's temp root (decision test-temp-standard).
A repo's birth commit holds the debts and a defective app/value.txt. Its fix commit, the base, holds the fix and the
tests added later. A fixture test script writes its name and its working folder to the file named by RETIRE_MARKS
before it asserts, so a case shows where a Retire check ran from that file. No case waits on a clock. The Retire-run
cases pass a fake run_state, so no case reads the network.
"""
import atexit, json, os, shutil, subprocess, sys, tempfile, unittest, unittest.mock

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


def script(body, imports=""):
    """A unittest fixture script. Its mark comes before its imports, so a birth tree that cannot import still leaves one."""
    return ("import os, unittest\n"
            "with open(os.environ['RETIRE_MARKS'], 'a', encoding='utf-8') as f:\n"
            "    f.write(os.path.basename(__file__) + ' ' + os.getcwd() + '\\n')\n"
            + imports
            + "class Case(unittest.TestCase):\n"
            "    def test_it(self):\n"
            "        " + body + "\n"
            "if __name__ == '__main__':\n"
            "    unittest.main()\n")


def value_is(word):
    """A script that asserts app/value.txt holds `word`: red on the birth commit, where the value is the defect."""
    return script("with open('app/value.txt', encoding='utf-8') as f: self.assertEqual(f.read(), '%s\\n')" % word)


PASS_PY = value_is("good")
FAIL_PY = script("self.fail('this test always fails')")
WEAK_PY = script("self.assertTrue(True)")  # passes on any tree, so it never catches the defect
LATER_PY = script("with open('app/later.txt', encoding='utf-8') as f: self.assertEqual(f.read(), 'later\\n')")
NEWMOD_PY = script("self.assertEqual(VALUE, 1)", imports="from newmod import VALUE\n")

NODE_IMPORTS = ("import fs from 'node:fs';\n"
                "import assert from 'node:assert/strict';\n"
                "import { test } from 'node:test';\n")


def node_script(name, body):
    """A node --test fixture: its mark, then `body`. The mark comes before any `await import`, so a failed import leaves one."""
    return NODE_IMPORTS + "fs.appendFileSync(process.env.RETIRE_MARKS, '%s ' + process.cwd() + '\\n');\n" % name + body


VALUE_MJS = node_script("test_value.mjs", "test('the value is good', () => assert.equal(fs.readFileSync('app/value.txt', 'utf-8'), 'good\\n'));\n")
WEAK_MJS = node_script("test_weak.mjs", "test('passes', () => assert.ok(true));\n")
NODEMOD_MJS = node_script("test_nodemod.mjs", "const { VALUE } = await import('./newmod.mjs');\n"
                                              "test('the module value is 1', () => assert.equal(VALUE, 1));\n")

EXTRAS = {"kinds": {}, "rolled-out": True}  # a rolled-out repo keeps debts at docs/debts
BASE = {  # the birth commit's files; app/value.txt holds the defect
    ".claude/layout-extras.json": json.dumps(EXTRAS) + "\n",
    "docs/debts/README.md": "# Debts\n\n- **Retire.** Run `tests/test_fail.py`.\n",  # a README is not a debt, even with a Retire line
    "docs/debts/notes.md": "# Notes\n\n- **Retire.** Run `tests/test_fail.py`.\n",
    "app/value.txt": "bad\n",
    "tests/test_pass.py": PASS_PY,
    "tests/test_fail.py": FAIL_PY,
    "tests/test_weak.py": WEAK_PY,
    "tests/test_pass.mjs": "export {};\n",
    "tests/test_value.mjs": VALUE_MJS,
    "tests/test_weak.mjs": WEAK_MJS,
}
FIX = {  # the fix commit: the base of a repo built with fixed=True. The tests here were added after the birth.
    "app/value.txt": "good\n",
    "app/later.txt": "later\n",
    "tests/newmod.py": "VALUE = 1\n",
    "tests/newmod.mjs": "export const VALUE = 1;\n",
    "tests/test_newmod.py": NEWMOD_PY,
    "tests/test_reads_later.py": LATER_PY,
    "tests/test_nodemod.mjs": NODEMOD_MJS,
}
WHAT = "A finding the Retire check closes, written out in full so that a rename keeps most of this text. " * 2
PASS = "Delete the old helper. Check: `tests/test_pass.py`."
FAIL = "Delete the old helper. Check: `tests/test_fail.py`."
WEAK = "Delete the old helper. Check: `tests/test_weak.py`."
PASS_THEN_WEAK = "Delete the old helper. Check: `tests/test_pass.py` then `tests/test_weak.py`."
NEWMOD = "Delete the old helper. Check: `tests/test_newmod.py`."
LATER = "Delete the old helper. Check: `tests/test_reads_later.py`."
MISSING = "Delete the old helper. Check: `lint/test_gone.py`."
NODE_PASS = "Delete the old helper. Check: `tests/test_value.mjs`."
NODE_WEAK = "Delete the old helper. Check: `tests/test_weak.mjs`."
NODE_IMPORT = "Delete the old helper. Check: `tests/test_nodemod.mjs`."
PROSE = "Delete the old helper once nothing reads it."
RUN_URL = "https://github.com/fixture/repo/actions/runs/42"
ATTRIBUTION = "\U0001F916 Generated with [Claude Code](https://claude.com/claude-code)"


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


class Case(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="case-", dir=RUN)
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.marks = os.path.join(self.folder, "marks.txt")
        patch = unittest.mock.patch.dict(os.environ, {"RETIRE_MARKS": self.marks})
        patch.start()
        self.addCleanup(patch.stop)
        self.dir = self.base = self.head = None

    def repo(self, debts=None, folder="docs/debts", extras=None, rolled=True, fixed=True, birth_files=None):
        """A repo whose birth commit holds BASE, the debts ({name: Retire text}) in `folder`, `extras` as its layout file, and
        `birth_files` ({path: text}) over the rest. With `fixed`, a fix commit (FIX) on top becomes the base; without it the base
        is the birth commit. `rolled=False` drops the layout file, so the repo keeps its debts where the legacy map puts them."""
        self.dir = tempfile.mkdtemp(prefix="repo-", dir=self.folder)
        sh(self.dir, "git", "init", "-q", "-b", "main")
        files = dict(BASE)
        if not rolled:
            del files[".claude/layout-extras.json"]
        for name, retire in (debts or {}).items():
            files["%s/%s.md" % (folder, name)] = debt(retire)
        if extras is not None:
            files[".claude/layout-extras.json"] = json.dumps(extras) + "\n"
        files.update(birth_files or {})
        self.commit(files, "birth")
        if fixed:
            self.commit(FIX, "fix")
        self.base = self.head = sh(self.dir, "git", "rev-parse", "HEAD")

    def commit(self, files, message):
        for path, text in files.items():
            put(os.path.join(self.dir, path), text)
        sh(self.dir, "git", "add", "-A")
        sh(self.dir, "git", "commit", "-q", "-m", message)

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

    def _runs(self):
        """(script name, working folder) for each fixture script that ran, in the order it ran."""
        try:
            with open(self.marks, encoding="utf-8") as f:
                return [tuple(line.split(" ", 1)) for line in f.read().splitlines()]
        except FileNotFoundError:
            return []

    def ran(self):
        """(script name, working folder) for each fixture script that ran in the head folder."""
        return [run for run in self._runs() if run[1] == self.dir]

    def ran_at_birth(self):
        """The names of the fixture scripts that ran in another folder (the birth commit's scratch tree), in the order they ran."""
        return [name for name, folder in self._runs() if folder != self.dir]

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
    """A debt file deleted between base and head is a close, and its Retire check runs on the head and on the birth commit."""

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

    def test_4c_a_retire_naming_a_test_the_pr_deletes_is_red(self):
        """A backticked test path the head does not track reads red (coordinator ruling 2026-11-07 15:06 CST)."""
        self.repo(debts={"d-gone": PASS})
        self.change(rm=["docs/debts/d-gone.md", "tests/test_pass.py"])
        found = self.findings()
        self.assertEqual(self.ran(), [], "a test the head no longer tracks ran")
        self.assertEqual(pairs(found), [("d-gone", "red")], "a backticked test path the head does not track did not read as red")

    def test_4d_a_lone_backtick_in_retire_prose_does_not_swallow_the_real_span(self):
        self.repo(debts={"d-tick": "Mind the lone ` mark. Check: `tests/test_pass.py`."})
        self.change(rm=["docs/debts/d-tick.md"])
        found = self.findings()
        self.assertEqual(self.ran(), [("test_pass.py", self.dir)], "the real span after a lone backtick did not run")
        self.assertEqual(pairs(found), [], "a lone backtick made the Retire read as prose")

    def test_4e_a_retire_naming_a_test_the_head_never_tracked_is_red(self):
        self.repo(debts={"d-missing": MISSING})
        self.change(rm=["docs/debts/d-missing.md"])
        found = self.findings()
        self.assertEqual(self.ran(), [], "a test the head does not track ran")
        self.assertEqual(pairs(found), [("d-missing", "red")], "a backticked test path the head never tracked did not read as red")
        self.assertIn("lint/test_gone.py", found[0].text, "the red finding does not name the missing test")

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
        self.change(write={"tests/test_pass.py": PASS_PY + "# touched\n"})
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


class Birth(Case):
    """A close's Retire test must go green on the head and red on the debt's birth commit, the commit that added the debt.
    The birth tree holds the defect; the head's copy of the named test runs there."""

    def test_b1_a_fix_in_the_pr_whose_test_catches_the_defect_passes(self):
        self.repo(debts={"d-fix": PASS}, fixed=False)
        self.change(write={"app/value.txt": "good\n"}, rm=["docs/debts/d-fix.md"])
        found = self.findings()
        self.assertEqual(self.ran(), [("test_pass.py", self.dir)], "the Retire check did not run in the head folder")
        self.assertEqual(pairs(found), [], "a test that catches the defect, fixed in the PR, gave a finding")

    def test_b2_a_fix_in_the_pr_whose_test_passes_on_the_defect_is_red(self):
        self.repo(debts={"d-weak": WEAK}, fixed=False)
        self.change(write={"app/value.txt": "good\n"}, rm=["docs/debts/d-weak.md"])
        found = self.findings()
        self.assertEqual(self.ran_at_birth(), ["test_weak.py"], "the Retire check did not run on the birth commit")
        self.assertEqual(pairs(found), [("d-weak", "red")], "a test that passes on the birth commit's defect gave no red finding")

    def test_b3_a_docs_only_close_whose_test_catches_the_defect_passes(self):
        self.repo(debts={"d-docs": PASS})
        self.change(rm=["docs/debts/d-docs.md"])
        found = self.findings()
        self.assertEqual(self.ran(), [("test_pass.py", self.dir)], "the Retire check did not run in the head folder")
        self.assertEqual(pairs(found), [], "a docs-only close, fixed before the base, gave a finding")

    def test_b4_a_docs_only_close_whose_test_passes_on_the_defect_is_red(self):
        self.repo(debts={"d-docs-weak": WEAK})
        self.change(rm=["docs/debts/d-docs-weak.md"])
        found = self.findings()
        self.assertEqual(self.ran_at_birth(), ["test_weak.py"], "the Retire check did not run on the birth commit")
        self.assertEqual(pairs(found), [("d-docs-weak", "red")], "a docs-only close whose test passes on the defect gave no red finding")

    def test_b5_a_test_that_cannot_import_on_the_birth_commit_is_unknown(self):
        self.repo(debts={"d-imp": NEWMOD})
        self.change(rm=["docs/debts/d-imp.md"])
        found = self.findings()
        self.assertEqual(self.ran_at_birth(), ["test_newmod.py"], "the Retire check did not run on the birth commit")
        self.assertEqual(pairs(found), [("d-imp", "unknown")], "a test whose import fails on the birth commit did not read as unknown")

    def test_b6_a_cite_clears_the_unknown_of_a_test_that_cannot_import_on_the_birth_commit(self):
        self.repo(debts={"d-imp": NEWMOD})
        self.change(rm=["docs/debts/d-imp.md"])
        runs = Runs(("success", self.head))
        found = self.findings(pr_body="Retire-run: d-imp -- %s\n" % RUN_URL, run_state=runs)
        self.assertEqual(pairs(found), [], "a green cite did not clear the unknown of a test that cannot import on the birth commit")

    @unittest.skip("TODO: the written-reason form is not built yet. Set its PR-body line here, then unskip.")
    def test_b7_a_written_reason_clears_an_unknown_check(self):
        self.repo(debts={"d-imp": NEWMOD})
        self.change(rm=["docs/debts/d-imp.md"])
        found = self.findings(pr_body="TODO: the written-reason line")
        self.assertEqual(pairs(found), [], "a written reason did not clear an unknown check")

    def test_b8_every_span_is_checked_when_an_earlier_span_is_red_on_the_birth_commit(self):
        self.repo(debts={"d-two": PASS_THEN_WEAK})
        self.change(rm=["docs/debts/d-two.md"])
        found = self.findings()
        self.assertEqual(sorted(self.ran_at_birth()), ["test_pass.py", "test_weak.py"], "a span after a birth-red span did not run on the birth commit")
        self.assertEqual(pairs(found), [("d-two", "red")], "the weak span after a birth-red span gave no red finding")

    def test_b9_an_errors_only_run_on_the_birth_commit_is_unknown(self):
        self.repo(debts={"d-err": LATER})
        self.change(rm=["docs/debts/d-err.md"])
        found = self.findings()
        self.assertEqual(self.ran_at_birth(), ["test_reads_later.py"], "the Retire check did not run on the birth commit")
        self.assertEqual(pairs(found), [("d-err", "unknown")], "a run that only errors on the birth commit did not read as unknown")

    def test_b10_the_birth_is_the_oldest_add_not_the_last_touch(self):
        self.repo(debts={"d-touch": PASS}, fixed=False)  # the debt is added with the defect
        self.change(write={"app/value.txt": "good\n", "docs/debts/d-touch.md": debt(PASS).replace(WHAT, WHAT + " Edited later.")})
        self.base = self.head  # a later commit fixes the defect and touches the debt
        self.change(rm=["docs/debts/d-touch.md"])
        found = self.findings()
        self.assertEqual(self.ran(), [("test_pass.py", self.dir)], "the Retire check did not run in the head folder")
        self.assertEqual(pairs(found), [], "a debt touched after its defect was fixed read that later commit as its birth")

    def test_b11_the_birth_tree_runs_the_head_copy_of_the_named_test_not_its_own(self):
        self.repo(debts={"d-overlay": PASS}, fixed=False, birth_files={"tests/test_pass.py": WEAK_PY})  # the birth's copy passes anything
        self.change(write={"app/value.txt": "good\n", "tests/test_pass.py": PASS_PY}, rm=["docs/debts/d-overlay.md"])
        found = self.findings()
        self.assertEqual(self.ran(), [("test_pass.py", self.dir)], "the head's copy did not run in the head folder")
        self.assertEqual(pairs(found), [], "the birth commit ran its own weak copy of the test, not the head's copy that catches the defect")


@unittest.skipUnless(shutil.which("node"), "node is not on PATH, so the node --test cases cannot run")
class Node(Case):
    """A node --test span follows the same rule as a Python one: green on the head, red on the birth, unknown on an import error."""

    def test_n1_a_fix_in_the_pr_whose_node_test_catches_the_defect_passes(self):
        self.repo(debts={"d-node-fix": NODE_PASS}, fixed=False)
        self.change(write={"app/value.txt": "good\n"}, rm=["docs/debts/d-node-fix.md"])
        found = self.findings()
        self.assertEqual(self.ran(), [("test_value.mjs", self.dir)], "the node check did not run in the head folder")
        self.assertEqual(pairs(found), [], "a node test that catches the defect, fixed in the PR, gave a finding")

    def test_n2_a_node_test_that_passes_on_the_defect_is_red(self):
        self.repo(debts={"d-node-weak": NODE_WEAK}, fixed=False)
        self.change(write={"app/value.txt": "good\n"}, rm=["docs/debts/d-node-weak.md"])
        found = self.findings()
        self.assertEqual(self.ran_at_birth(), ["test_weak.mjs"], "the node check did not run on the birth commit")
        self.assertEqual(pairs(found), [("d-node-weak", "red")], "a node test that passes on the birth commit's defect gave no red finding")

    def test_n3_a_node_test_whose_import_fails_on_the_birth_commit_is_unknown(self):
        self.repo(debts={"d-node-imp": NODE_IMPORT})
        self.change(rm=["docs/debts/d-node-imp.md"])
        found = self.findings()
        self.assertEqual(self.ran_at_birth(), ["test_nodemod.mjs"], "the node check did not run on the birth commit")
        self.assertEqual(pairs(found), [("d-node-imp", "unknown")], "a node test whose import fails on the birth commit did not read as unknown")


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

    def test_r3_a_cite_of_a_green_run_on_an_older_commit_is_red(self):
        self.closed_prose()
        runs = Runs(("success", self.base))  # the parent of the PR head: an ancestor, not a descendant
        found = self.findings(pr_body="Retire-run: d-prose -- %s\n" % RUN_URL, run_state=runs)
        self.assertEqual(pairs(found), [("d-prose", "red")], "a green run on an older commit cleared the debt")

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

    def test_r10_a_green_cite_does_not_clear_a_debt_whose_test_passes_on_the_defect(self):
        self.repo(debts={"d-weak-cite": WEAK})
        self.change(rm=["docs/debts/d-weak-cite.md"])
        runs = Runs(("success", self.head))
        found = self.findings(pr_body="Retire-run: d-weak-cite -- %s\n" % RUN_URL, run_state=runs)
        self.assertEqual(self.ran_at_birth(), ["test_weak.py"], "the Retire check did not run on the birth commit")
        self.assertEqual(pairs(found), [("d-weak-cite", "red")], "a green cite cleared a test that passes on the birth commit's defect")


if __name__ == "__main__":
    unittest.main()
