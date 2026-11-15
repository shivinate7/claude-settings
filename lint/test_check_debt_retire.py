#!/usr/bin/env python3
"""Fixture suite for lint/check_debt_retire.py. Run: python3 lint/test_check_debt_retire.py

Every case builds a throwaway git repo in its own folder under this run's temp root (decision test-temp-standard),
commits a base and a head, and asks the check for its findings. A fixture test script appends its own name and its
working folder to the file named by RETIRE_MARKS, so a case shows that a Retire check ran, or did not, from that file.
No case waits on a clock. The Retire-run cases pass a fake run_state, and the CI-step cases a fake ci_steps reader, so no case reads the network.
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
SESSION_URL = "https://claude.ai/code/session_013NEJL2SdAA1CCG5eTFVFVr"
NO_RETIRED = "check_debt_retire has no retired(): a Retire-run cite cannot excuse a debt close (decision debt-close-runs-retire)"
NO_CI_CHECK = ("check() has no ci_steps, draft or deferred parameter: a debt close whose Retire suite a CI step runs is not judged "
               "from the PR's CI run yet (ruling 2026-11-14 20:32 CST)")
WORKFLOW = ".github/workflows/checks.yml"


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


def checks_yml(run="python3 tests/test_fail.py", name="Guard suite", jobs=("shard-1", "shard-2")):
    """A head workflow: one job per name in `jobs`, each with one step `name` that runs `run`. Two jobs, as two shards of a suite are."""
    out = ["name: checks", "on: pull_request", "jobs:"]
    for job in jobs:
        out += ["  %s:" % job, "    runs-on: ubuntu-latest", "    steps:", "      - uses: actions/checkout@v4",
                "      - name: %s" % name, "        run: %s" % run]
    return "\n".join(out) + "\n"


def big_workflow():
    """Twelve jobs of six steps each. The suite is step 4 of job-03 and of job-07; no other step names it."""
    out = ["name: checks", "on: pull_request", "jobs:"]
    for j in range(12):
        out += ["  job-%02d:" % j, "    runs-on: ubuntu-latest", "    steps:"]
        for s in range(6):
            run = "python3 tests/test_fail.py" if s == 4 and j in (3, 7) else "echo step %d of job %d" % (s, j)
            out += ["      - name: step %d" % s, "        run: %s" % run]
    return "\n".join(out) + "\n"


def ci_row(job, conclusion="success", status="completed", sha=None, name="Guard suite"):
    """One step of the PR's CI run, as the reader gives it: {job, name, conclusion, status, run_sha}."""
    return {"job": job, "name": name, "conclusion": conclusion, "status": status, "run_sha": sha}


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


class Isolated(Case):
    """An isolated run (the merge tool and the CLI) gives the scratch worktree the checkout's installed packages (decision debt-close-runs-retire)."""

    NEEDS_DEPS = ("import os, sys\n"
                  "sys.exit(0 if os.path.isdir(os.path.join('node_modules', 'marker')) else 1)\n")

    def deps_repo(self, nested=False):
        retire = "Delete the helper. Check: `tests/test_deps.py`" + (" and `tests/test_deps_sub.py`." if nested else ".")
        self.repo(debts={"d-deps": retire})
        self.change(write={"tests/test_deps.py": self.NEEDS_DEPS, "package.json": "{}\n", ".gitignore": "node_modules/\n",
                           **({"sub/package.json": "{}\n", "tests/test_deps_sub.py": self.NEEDS_DEPS.replace("'node_modules'", "'sub', 'node_modules'")}
                              if nested else {})})
        self.base = self.head
        self.change(rm=["docs/debts/d-deps.md"])
        for pre in ("", "sub") if nested else ("",):
            put(os.path.join(self.dir, pre, "node_modules", "marker", "x"), "x")

    def isolated(self, where=None):
        return D.check(where or self.dir, self.base, head=self.head, isolate=True)

    def fresh_worktree(self):
        """A detached worktree of the head with no node_modules of its own: the shape the merge tool runs a Retire check in."""
        wt = os.path.join(self.folder, "wt")
        sh(self.dir, "git", "worktree", "add", "-q", "--detach", wt, self.head)
        self.addCleanup(sh, self.dir, "git", "worktree", "remove", "--force", wt)
        return wt

    def test_i1_installed_packages_reach_the_scratch_worktree(self):
        self.deps_repo()
        self.assertEqual(pairs(self.isolated()), [], "a scratch run did not see the checkout's node_modules")

    def test_i2_a_nested_package_folder_gets_its_packages_too(self):
        self.deps_repo(nested=True)
        self.assertEqual(pairs(self.isolated()), [], "a nested node_modules did not reach the scratch worktree")

    def test_i2b_a_nested_package_folder_without_packages_is_red(self):
        self.deps_repo(nested=True)
        shutil.rmtree(os.path.join(self.dir, "sub", "node_modules"))
        self.assertEqual(pairs(self.isolated()), [("d-deps", "red")], "the nested test passed without sub/node_modules")

    def test_i3_a_checkout_with_no_packages_still_runs_the_test_and_it_is_red(self):
        self.deps_repo()
        shutil.rmtree(os.path.join(self.dir, "node_modules"))
        self.assertEqual(pairs(self.isolated()), [("d-deps", "red")], "a test that fails with no packages stopped being red")

    def test_i4_a_real_red_test_stays_red_with_packages_linked(self):
        self.repo(debts={"d-fail": FAIL})
        self.change(write={"package.json": "{}\n", ".gitignore": "node_modules/\n"}, rm=["docs/debts/d-fail.md"])
        put(os.path.join(self.dir, "node_modules", "marker", "x"), "x")
        self.assertEqual(pairs(self.isolated()), [("d-fail", "red")], "linking packages hid a failing test")

    def test_i5_the_scratch_link_does_not_remove_the_checkouts_packages(self):
        self.deps_repo()
        self.isolated()
        self.assertTrue(os.path.isfile(os.path.join(self.dir, "node_modules", "marker", "x")), "cleanup deleted the real node_modules")

    def test_i6_a_fresh_worktree_of_an_installed_checkout_gets_the_checkouts_packages(self):
        self.deps_repo()
        wt = self.fresh_worktree()
        self.assertFalse(os.path.lexists(os.path.join(wt, "node_modules")), "scope: the fresh worktree already has node_modules")
        self.assertEqual(pairs(self.isolated(wt)), [], "a fresh worktree did not reach the installed checkout's node_modules")

    def test_i6b_a_fresh_worktree_with_no_packages_anywhere_is_red(self):
        self.deps_repo()
        shutil.rmtree(os.path.join(self.dir, "node_modules"))
        wt = self.fresh_worktree()
        self.assertFalse(os.path.lexists(os.path.join(self.dir, "node_modules")), "scope: the checkout still has node_modules")
        self.assertEqual(pairs(self.isolated(wt)), [("d-deps", "red")], "a test with no packages anywhere stopped being red")

    def test_i6c_the_worktrees_own_packages_win_over_the_checkouts(self):
        self.deps_repo()
        wt = self.fresh_worktree()
        os.makedirs(os.path.join(wt, "node_modules"))  # wt's own install, without the marker
        self.assertFalse(os.path.exists(os.path.join(wt, "node_modules", "marker")), "scope: wt's own install has the marker")
        self.assertEqual(pairs(self.isolated(wt)), [("d-deps", "red")], "the checkout's packages replaced the worktree's own")

    def test_i6d_a_real_red_test_in_a_fresh_worktree_stays_red(self):
        self.repo(debts={"d-fail": FAIL})
        self.change(write={"package.json": "{}\n", ".gitignore": "node_modules/\n"}, rm=["docs/debts/d-fail.md"])
        put(os.path.join(self.dir, "node_modules", "marker", "x"), "x")
        wt = self.fresh_worktree()
        self.assertFalse(os.path.lexists(os.path.join(wt, "node_modules")), "scope: the fresh worktree already has node_modules")
        self.assertEqual(pairs(self.isolated(wt)), [("d-fail", "red")], "linking packages hid a failing test")

    def test_i7_a_relative_checkout_path_links_the_packages(self):
        self.deps_repo()
        here = os.getcwd()
        os.chdir(self.dir)
        self.addCleanup(os.chdir, here)
        self.assertTrue(os.path.isfile(os.path.join("node_modules", "marker", "x")), "scope: the checkout has no packages")
        self.assertEqual(pairs(self.isolated(".")), [], "a relative checkout path linked node_modules to itself")


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

    def test_r1c_a_session_url_line_after_the_attribution_does_not_hide_the_cite(self):
        self.closed_prose()
        plain = "Summary.\n\nRetire-run: d-prose -- %s\n\n%s\n" % (RUN_URL, ATTRIBUTION)
        self.assertEqual(pairs(self.findings(pr_body=plain, run_state=Runs(("success", self.head)))), [],
                         "scope: the body without the session URL line did not clear the prose debt")
        runs = Runs(("success", self.head))
        body = "Summary.\n\nRetire-run: d-prose -- %s\n\n%s\n\n%s\n" % (RUN_URL, ATTRIBUTION, SESSION_URL)
        found = self.findings(pr_body=body, run_state=runs)
        self.assertEqual(runs.urls, [RUN_URL], "a session URL line after the attribution hid the Retire-run cite")
        self.assertEqual(pairs(found), [], "a session URL line after the attribution left the prose debt standing")

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


class CiSteps(Case):
    """A debt whose Retire names a suite that a CI step runs is judged from the PR's own CI run, and that suite never runs here
    (ruling 2026-11-14 20:32 CST). The suite is tests/test_fail.py: red if a run here reaches it, and it leaves a mark, so ran() shows a local run."""

    def ci_findings(self, ci_steps=None, draft=False, pr_body="", run_state=None, head=None):
        """check() with the CI-step read and the draft flag. The deferred list is self.deferred. A check without the parameters is a named red."""
        self.assertTrue({"ci_steps", "draft", "deferred"} <= set(inspect.signature(D.check).parameters), NO_CI_CHECK)
        self.deferred = []
        return D.check(self.dir, self.base, head=head or self.head, pr_body=pr_body, run_state=run_state,
                       ci_steps=ci_steps, draft=draft, deferred=self.deferred)

    def ci_close(self, retire=FAIL, files=None):
        """The base holds the debt `d-ci` with `retire`. The head deletes it and adds `files` (default: a workflow whose two shard jobs run the suite)."""
        self.repo(debts={"d-ci": retire})
        self.change(write={WORKFLOW: checks_yml()} if files is None else files, rm=["docs/debts/d-ci.md"])

    def test_c1_a_draft_defers_a_close_whose_ci_step_runs_its_suite_and_runs_that_suite_nowhere(self):
        self.ci_close()
        found = self.ci_findings(ci_steps=Runs([]), draft=True)
        self.assertEqual(self.ran(), [], "a draft ran a suite that a CI step runs, so the suite runs twice")
        self.assertEqual(pairs(found), [], "a draft's close gave a finding: a deferred close neither passes nor refuses")
        self.assertEqual(len(self.deferred), 1, "the draft's close is not in the deferred list")
        self.assertIn("d-ci", str(self.deferred[0]), "the deferred entry does not name the debt")

    def test_c2_a_draft_still_runs_a_suite_no_ci_step_names_here(self):
        self.ci_close(files={WORKFLOW: checks_yml(run="python3 tests/test_pass.py")})
        found = self.ci_findings(ci_steps=Runs([ci_row("shard-1", sha=self.head)]), draft=True)
        self.assertEqual(self.ran(), [("test_fail.py", self.dir)], "a draft did not run a suite that no CI step names")
        self.assertEqual(pairs(found), [("d-ci", "red")], "the local run of a suite no CI step names did not decide a draft's close")
        self.assertEqual(self.deferred, [], "a suite no CI step names was deferred")

    def test_c3_a_non_draft_with_both_shards_green_on_the_head_passes_and_runs_nothing_here(self):
        self.ci_close()
        reader = Runs([ci_row("shard-1", sha=self.head), ci_row("shard-2", sha=self.head)])
        found = self.ci_findings(ci_steps=reader)
        self.assertEqual(reader.urls, [self.head], "the CI steps of the PR head were not read")
        self.assertEqual(self.ran(), [], "a green CI run still ran the suite here")
        self.assertEqual(pairs(found), [], "two green CI steps on the PR head gave a finding")

    def test_c4_a_green_ci_run_on_a_commit_above_the_head_passes(self):
        self.ci_close()
        pr_head = self.head
        self.change(write={"notes/after.txt": "later\n"})  # the run's commit: one on top of the PR head
        reader = Runs([ci_row("shard-1", sha=self.head), ci_row("shard-2", sha=self.head)])
        found = self.ci_findings(ci_steps=reader, head=pr_head)
        self.assertEqual(reader.urls, [pr_head], "the CI steps of the PR head were not read")
        self.assertEqual(self.ran(), [], "a green CI run on a commit above the head still ran the suite here")
        self.assertEqual(pairs(found), [], "a green CI run on a descendant of the PR head did not pass the close")

    def test_c5_a_missing_ci_run_refuses_as_unknown_and_runs_nothing_here(self):
        self.ci_close()
        found = self.ci_findings(ci_steps=Runs([]))
        self.assertEqual(self.ran(), [], "a missing CI run sent the suite to a local run")
        self.assertEqual(pairs(found), [("d-ci", "unknown")], "a missing CI run did not refuse as unknown")

    def test_c6_a_ci_step_still_running_refuses_as_unknown_and_runs_nothing_here(self):
        self.ci_close()
        reader = Runs([ci_row("shard-1", sha=self.head), ci_row("shard-2", conclusion=None, status="in_progress", sha=self.head)])
        found = self.ci_findings(ci_steps=reader)
        self.assertEqual(self.ran(), [], "a CI step still running sent the suite to a local run")
        self.assertEqual(pairs(found), [("d-ci", "unknown")], "a CI step still running did not refuse as unknown")

    def test_c7_a_red_ci_step_refuses_as_red_and_runs_nothing_here(self):
        self.ci_close()
        reader = Runs([ci_row("shard-1", conclusion="failure", sha=self.head), ci_row("shard-2", sha=self.head)])
        found = self.ci_findings(ci_steps=reader)
        self.assertEqual(self.ran(), [], "a red CI step sent the suite to a local run")
        self.assertEqual(pairs(found), [("d-ci", "red")], "a red CI step did not refuse as red")

    def test_c8_a_ci_run_on_another_head_refuses_as_unknown_and_runs_nothing_here(self):
        self.ci_close()
        tree = sh(self.dir, "git", "rev-parse", self.head + "^{tree}")
        other = sh(self.dir, "git", "commit-tree", tree, "-m", "a commit of another head")  # unrelated to the PR head
        self.assertNotEqual(subprocess.run(["git", "merge-base", "--is-ancestor", self.head, other], cwd=self.dir, capture_output=True).returncode, 0,
                            "scope: the other commit is on the PR head's history")
        reader = Runs([ci_row("shard-1", sha=other), ci_row("shard-2", sha=other)])
        found = self.ci_findings(ci_steps=reader)
        self.assertEqual(self.ran(), [], "a CI run of another head sent the suite to a local run")
        self.assertEqual(pairs(found), [("d-ci", "unknown")], "a CI run of another head did not refuse as unknown")

    def test_c9_a_ci_read_that_raises_refuses_as_unknown_and_runs_nothing_here(self):
        self.ci_close()
        found = self.ci_findings(ci_steps=Runs(RuntimeError("the run list read failed: HTTP 502")))
        self.assertEqual(self.ran(), [], "a CI read that raised sent the suite to a local run")
        self.assertEqual(pairs(found), [("d-ci", "unknown")], "a CI read that raised did not refuse as unknown")

    def test_c10_a_ci_read_that_returns_garbage_refuses_as_unknown(self):
        self.ci_close()
        found = self.ci_findings(ci_steps=Runs("not a list of steps"))
        self.assertEqual(self.ran(), [], "a garbage CI read sent the suite to a local run")
        self.assertEqual(pairs(found), [("d-ci", "unknown")], "a garbage CI read did not refuse as unknown")

    def test_c11_a_skipped_shard_falls_back_to_the_local_run_and_one_green_shard_does_not_clear_it(self):
        self.ci_close()
        reader = Runs([ci_row("shard-1", sha=self.head), ci_row("shard-2", conclusion="skipped", sha=self.head)])
        found = self.ci_findings(ci_steps=reader)
        self.assertEqual(self.ran(), [("test_fail.py", self.dir)], "a skipped CI step did not fall back to a local run of its suite")
        self.assertEqual(pairs(found), [("d-ci", "red")], "the local run a skipped step fell back to did not decide the close")

    def test_c12_two_skipped_shards_fall_back_to_the_local_run_which_passes_here(self):
        self.ci_close(retire=PASS, files={WORKFLOW: checks_yml(run="python3 tests/test_pass.py")})
        reader = Runs([ci_row("shard-1", conclusion="skipped", sha=self.head), ci_row("shard-2", conclusion="skipped", sha=self.head)])
        found = self.ci_findings(ci_steps=reader)
        self.assertEqual(self.ran(), [("test_pass.py", self.dir)], "two skipped CI steps did not fall back to a local run of their suite")
        self.assertEqual(pairs(found), [], "the local run that two skipped steps fell back to did not pass the close")

    def test_c13_a_head_with_no_workflow_file_runs_the_suite_here_even_with_a_green_reader(self):
        self.ci_close(files={})
        reader = Runs([ci_row("shard-1", sha=self.head), ci_row("shard-2", sha=self.head)])  # green: a read that decided here would pass the close
        found = self.ci_findings(ci_steps=reader)
        self.assertEqual(self.ran(), [("test_fail.py", self.dir)], "a head with no workflow file did not run the suite here")
        self.assertEqual(pairs(found), [("d-ci", "red")], "a suite no workflow names did not decide the close by its local run")

    def test_c14_a_debt_with_no_retire_line_stays_a_prose_finding_on_a_draft(self):
        self.repo()
        put(os.path.join(self.dir, "docs/debts/d-none.md"), "# A debt\n\n- **What.** %s\n- **Where.** None.\n- **Decision.** none\n" % WHAT)
        sh(self.dir, "git", "add", "-A")
        sh(self.dir, "git", "commit", "-q", "-m", "a debt with no Retire line")
        self.base = self.head = sh(self.dir, "git", "rev-parse", "HEAD")
        self.change(rm=["docs/debts/d-none.md"])
        found = self.ci_findings(ci_steps=Runs([ci_row("shard-1", sha=self.head)]), draft=True)
        self.assertEqual(self.deferred, [], "a debt with no Retire line was deferred")
        self.assertEqual(pairs(found), [("d-none", "prose")], "a debt with no Retire line stopped being a prose finding on a draft")

    def test_c15_a_green_cited_run_still_clears_a_prose_close_on_a_draft_and_is_read(self):
        self.repo(debts={"d-prose": PROSE})
        self.change(rm=["docs/debts/d-prose.md"])
        runs = Runs(("success", self.head))
        found = self.ci_findings(ci_steps=Runs([]), draft=True, pr_body="Retire-run: d-prose -- %s\n" % RUN_URL, run_state=runs)
        self.assertEqual(runs.urls, [RUN_URL], "a draft's prose close did not read its cited run")
        self.assertEqual(pairs(found), [], "a green cited run did not clear a draft's prose close")

    def test_c16_a_green_cited_run_never_clears_a_red_ci_step(self):
        self.ci_close()
        reader = Runs([ci_row("shard-1", conclusion="failure", sha=self.head), ci_row("shard-2", sha=self.head)])
        found = self.ci_findings(ci_steps=reader, pr_body="Retire-run: d-ci -- %s\n" % RUN_URL, run_state=Runs(("success", self.head)))
        self.assertEqual(self.ran(), [], "a red CI step sent the suite to a local run, where a cite could clear it")
        self.assertEqual(pairs(found), [("d-ci", "red")], "a green cited run cleared a red CI step")

    def test_c17_a_commented_out_step_that_names_the_suite_does_not_count(self):
        """The suite is named only in a comment. A scanner that reads a comment as a step would find a CI step and skip the local run."""
        wf = ("name: checks\non: pull_request\njobs:\n  shard-1:\n    runs-on: ubuntu-latest\n    steps:\n"
              "      - name: Guard suite\n        run: python3 tests/test_pass.py\n"
              "  # shard-2:\n  #   runs-on: ubuntu-latest\n  #   steps:\n  #     - name: Guard suite\n  #       run: python3 tests/test_fail.py\n")
        self.ci_close(files={WORKFLOW: wf})
        found = self.ci_findings(ci_steps=Runs([ci_row("shard-1", sha=self.head)]))
        self.assertEqual(self.ran(), [("test_fail.py", self.dir)], "a commented-out step counted as a CI step, so the suite did not run here")
        self.assertEqual(pairs(found), [("d-ci", "red")], "the commented-out step decided the close instead of the local run")

    def test_c18_a_hash_inside_a_quoted_run_does_not_cut_the_step_short(self):
        self.ci_close(files={WORKFLOW: checks_yml(run="'echo \"shard # 1 of 2\"; python3 tests/test_fail.py'")})
        reader = Runs([ci_row("shard-1", sha=self.head), ci_row("shard-2", sha=self.head)])
        found = self.ci_findings(ci_steps=reader)
        self.assertEqual(self.ran(), [], "a # inside a quoted run cut the step short, so the suite ran here")
        self.assertEqual(pairs(found), [], "two green steps whose quoted run names the suite gave a finding")

    def test_c19_a_block_run_that_names_the_suite_on_a_later_line_counts_as_a_ci_step(self):
        block = ("name: checks\non: pull_request\njobs:\n"
                 "  shard-1:\n    runs-on: ubuntu-latest\n    steps:\n      - name: Guard suite\n        run: |\n          set -e\n          python3 tests/test_fail.py\n"
                 "  shard-2:\n    runs-on: ubuntu-latest\n    steps:\n      - name: Guard suite\n        run: |\n          python3 tests/test_fail.py\n")
        self.ci_close(files={WORKFLOW: block})
        reader = Runs([ci_row("shard-1", sha=self.head), ci_row("shard-2", sha=self.head)])
        found = self.ci_findings(ci_steps=reader)
        self.assertEqual(self.ran(), [], "a block run that names the suite on a later line did not count as a CI step")
        self.assertEqual(pairs(found), [], "two green block-run steps that name the suite gave a finding")

    def test_c20_a_lone_quote_in_a_comment_or_a_step_name_does_not_hide_the_step(self):
        self.ci_close(files={WORKFLOW: "# Don't edit this by hand.\n" + checks_yml(name="Don't skip the guard suite")})
        reader = Runs([ci_row("shard-1", name="Don't skip the guard suite", sha=self.head),
                       ci_row("shard-2", name="Don't skip the guard suite", sha=self.head)])
        found = self.ci_findings(ci_steps=reader)
        self.assertEqual(self.ran(), [], "a lone quote hid the step that names the suite, so the suite ran here")
        self.assertEqual(pairs(found), [], "two green steps with a quote in their name gave a finding")

    def test_c21_a_full_size_workflow_is_judged_per_named_step_not_per_job(self):
        """Twelve jobs of six steps. Step 5 of job-03 is red and names no suite, so it must not refuse the close the named steps pass."""
        self.ci_close(files={WORKFLOW: big_workflow()})
        rows = [ci_row("job-%02d" % j, name="step %d" % s, sha=self.head, conclusion="failure" if (j, s) == (3, 5) else "success")
                for j in range(12) for s in range(6)]
        reader = Runs(rows)
        found = self.ci_findings(ci_steps=reader)
        self.assertEqual(reader.urls, [self.head], "the CI steps of the PR head were not read for a full-size workflow")
        self.assertEqual(self.ran(), [], "a full-size workflow with its named steps green still ran the suite here")
        self.assertEqual(pairs(found), [], "a red step that names no suite refused the close: judged per job, not per named step")

    def test_c22_a_refusal_of_a_ci_judged_close_names_no_local_run_and_no_forced_route(self):
        """A remedy never names the action the rule refuses (rule git-remedy-never-names-target, check stack_reason_hygiene_case): the suite
        runs in CI, so a refusal offers no local run of it, and no forced or no-verify push."""
        self.ci_close()
        refusals = (("a missing CI run", Runs([])),
                    ("a red CI step", Runs([ci_row("shard-1", conclusion="failure", sha=self.head), ci_row("shard-2", sha=self.head)])))
        for name, reader in refusals:
            with self.subTest(refusal=name):
                found = self.ci_findings(ci_steps=reader)
                self.assertTrue(found, "scope: %s did not refuse the close" % name)
                text = " ".join(f.text for f in found)
                self.assertNotIn("python3 tests/test_fail.py", text, "%s: the remedy names a local run of the suite CI runs" % name)
                self.assertNotIn("--force", text, "%s: the remedy names a forced push" % name)
                self.assertNotIn("--no-verify", text, "%s: the remedy names a no-verify commit" % name)


class TemplateExcuses(unittest.TestCase):
    """The PR template's own excuse lines. A PR body starts from the template, so a live excuse line in it would excuse a
    path or a debt in every PR that keeps it (decision debt-close-runs-retire)."""

    RETIRE_LINE = "Retire-run: <slug> -- <run URL>"  # the template's untouched placeholder lines
    DROPS_LINE = "Drops-lines: <path> -- <reason>"

    def live(self, text):
        """The excuse keys `text` carries, read the way the checks read a PR body: Retire-run slugs, then Drops-lines paths.
        A key that starts with `<` is an untouched placeholder, which names nothing real, so it drops out."""
        keys = list(D.cites(text)) + list(D.undo.allowed(HERE, "HEAD..HEAD", text))
        return [k for k in keys if not k.startswith("<")]

    def template(self):
        with open(os.path.join(HERE, "..", ".github", "pull_request_template.md"), encoding="utf-8") as f:
            return f.read()

    def test_real_template_carries_no_live_excuse(self):
        self.assertEqual(self.live(self.template()), [], "the PR template carries a live excuse line, so a PR body that starts from it excuses something")

    def test_live_excuse_lines_in_the_template_are_read(self):
        text = self.template()
        mutated = (text.replace(self.RETIRE_LINE, "Retire-run: a-debt -- https://example.test/run/1")
                       .replace(self.DROPS_LINE, "Drops-lines: docs/a.md -- gone"))
        self.assertNotEqual(mutated, text, "scope: the template has no placeholder line to replace, so nothing was mutated")
        self.assertEqual(self.live(mutated), ["a-debt", "docs/a.md"], "the excuse read misses a live Retire-run or Drops-lines line")


if __name__ == "__main__":
    unittest.main()
