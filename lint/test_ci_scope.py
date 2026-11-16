#!/usr/bin/env python3
"""CLI tests for the scope detector (.github/scripts/ci-scope.sh) and the mod test runner (.github/scripts/mod-tests.sh).

Each scope case builds a scratch git repo, commits a base, commits the changed paths, runs the script
with EVENT and BASE_SHA set, and reads the name=value lines it wrote to $GITHUB_OUTPUT.
CI_SCOPE overrides the script path (for a successor). Needs bash on PATH. The mod runner cases build a
scratch tree with a copy of mod-tests.sh and run it there; they need node on PATH.

Output names pinned (the `scope` job re-exports them as job outputs):
  JOB_FLAGS  one per check job except the lint job `checks`: checks_windows, checks_windows_merge,
             checks_windows_rest, checks_macos, shell_macos, pointer_windows
  STEP_FLAGS code, guard, sweep, mods, shoot (the suite flags; shoot turns on the checks-shoot and checks-waiting-page jobs)
  LINT_FLAGS lint_red_run, lint_plan_refuter, lint_ruling_kind, lint_comment_narration (the four pull-request lint steps of
             the `checks` job; LintStepScope and LintStepWorkflow pin them)
  records_only_skip  true exactly when the records-only shortcut forced the 13 flags off (RecordsOnlyPush pins it)

Run with:  python3 lint/test_ci_scope.py -v
"""
import ast
import os
import re
import shutil
import subprocess
import tempfile
import unittest

import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import tracked_tree  # noqa: E402  copies the script under test into a scratch tree; rm_tree removes the run folder
from workflow_steps import job_block, job_workflow, step_blocks, step_key  # noqa: E402  the one home of the step parser
SCRIPT = os.environ.get("CI_SCOPE") or os.path.join(HERE, "..", ".github", "scripts", "ci-scope.sh")
JOB_FLAGS = ["checks_windows", "checks_windows_merge", "checks_windows_rest", "checks_macos", "shell_macos", "pointer_windows"]
STEP_FLAGS = ["code", "guard", "sweep", "mods", "shoot"]
# Flags derived from others, kept out of JOB_FLAGS so the exact-set cases below stay about the base flags:
# checks_windows_sweep is set with checks_windows_rest. checks_guard is set when both `code` and `guard` are set, or
# directly by the arm for actions/playwright-setup and .github/shoot (the paths checks-guard installs from).
DERIVED_FLAGS = ["checks_windows_sweep", "checks_guard"]
ALL = JOB_FLAGS + STEP_FLAGS
BASH = shutil.which("bash")
# This module's run folder (test-temp-standard). run() makes its scratch repos under it; the module teardown removes it.
RUN_DIR = None


def setUpModule():
    global RUN_DIR
    RUN_DIR = _test_temp.run_folder()


def tearDownModule():
    tracked_tree.rm_tree(RUN_DIR)


def git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def run(paths, event="pull_request", base="auto", existing=(), landed=None, head_ref="", green=None,
        green_sibling=False, green_head=None, contents=None, facts=None, merged=None):
    """-> {name: 'true'|'false'} the script wrote. `paths` are committed on top of one base commit. `head_ref` is HEAD_REF,
    empty when not given, so no HEAD_REF of the caller's environment reaches the script.
    `green` (a list of paths) is the pull request's earlier head, committed before the head commit, so the whole diff against
    the base holds it too. `green_sibling` puts that earlier head on a branch off the base instead: a commit HEAD does not
    descend from. GREEN_HEAD is the earlier head's sha (empty when there is none) unless `green_head` gives another value.
    `contents` maps a path to its text, in place of "changed". `merged` (a list of paths) is a base change the pull request did
    not make: a commit off the base that adds them, merged into the head with --no-ff, so HEAD is a merge commit as in CI.
    BASE_SHA is then that base commit, and PR_HEAD is the head commit's sha. Without `merged`, PR_HEAD is unset, whatever the
    caller's environment holds. `facts`, a dict, is filled with the earlier head's `green` sha, the `delta` and `delta_head`
    (git diff --name-only --no-renames GREEN_HEAD HEAD), `delta_pr_head` (the same to the head commit) and `ancestor`
    (GREEN_HEAD is an ancestor of HEAD)."""
    contents = contents or {}
    with tempfile.TemporaryDirectory(dir=RUN_DIR) as d:
        git(d, "init", "-q")
        git(d, "config", "user.email", "t@t")
        git(d, "config", "user.name", "t")
        git(d, "config", "commit.gpgsign", "false")
        # No background gc or maintenance after a commit: it can write into .git while the temp dir is removed.
        git(d, "config", "gc.auto", "0")
        git(d, "config", "maintenance.auto", "false")
        open(os.path.join(d, "seed.txt"), "w").write("seed\n")
        # The base holds landed-dirs.txt: the repo's own, or `landed` (a list of dir names) in its place.
        with open(os.path.join(HERE, "..", "landed-dirs.txt")) as f:
            real = f.read()
        open(os.path.join(d, "landed-dirs.txt"), "w").write(real if landed is None else chr(10).join(landed) + chr(10))
        for p in existing:  # in the base commit, so the head commit modifies them
            os.makedirs(os.path.dirname(os.path.join(d, p)), exist_ok=True)
            open(os.path.join(d, p), "w").write("old\n")
        git(d, "add", "-A")
        git(d, "commit", "-qm", "base")
        sha = git(d, "rev-parse", "HEAD")
        def write(names):
            for p in names:
                full = os.path.join(d, p)
                os.makedirs(os.path.dirname(full), exist_ok=True)
                open(full, "w").write(contents.get(p, "changed\n"))
        green_sha = ""
        if green is not None and green_sibling:
            git(d, "checkout", "-q", "-b", "side")
            write(green)
            git(d, "add", "-A")
            git(d, "commit", "-qm", "earlier head")
            green_sha = git(d, "rev-parse", "HEAD")
            git(d, "checkout", "-q", "-")
            # HEAD's line gets the same paths in a commit of its own, so the two trees differ by `paths` alone.
            write(green)
            git(d, "add", "-A")
            git(d, "commit", "-qm", "pr code")
        elif green is not None:
            write(green)
            git(d, "add", "-A")
            git(d, "commit", "-qm", "earlier head", "--allow-empty")
            green_sha = git(d, "rev-parse", "HEAD")
        write(paths)
        git(d, "add", "-A")
        git(d, "commit", "-qm", "head", "--allow-empty")
        head_sha = git(d, "rev-parse", "HEAD")
        base_sha = sha if base == "auto" else base
        if merged is not None:
            git(d, "checkout", "-q", "-b", "base-moved", sha)
            write(merged)
            git(d, "add", "-A")
            git(d, "commit", "-qm", "base change", "--allow-empty")
            if base == "auto":
                base_sha = git(d, "rev-parse", "HEAD")
            git(d, "checkout", "-q", "-")
            git(d, "merge", "-q", "--no-ff", "--no-edit", "base-moved")
        out = os.path.join(d, "..", f"out-{os.getpid()}.txt")
        env = dict(os.environ, EVENT=event, GITHUB_OUTPUT=out, HEAD_REF=head_ref,
                   BASE_SHA=base_sha, GREEN_HEAD=green_sha if green_head is None else green_head)
        env.pop("PR_HEAD", None)  # a caller's value never reaches the script; only `merged` sets it
        if merged is not None:
            env["PR_HEAD"] = head_sha
        if facts is not None and green_sha:
            delta_head = git(d, "diff", "--name-only", "--no-renames", green_sha, "HEAD").split()
            facts.update(green=green_sha, delta=delta_head, delta_head=delta_head,
                         delta_pr_head=git(d, "diff", "--name-only", "--no-renames", green_sha, head_sha).split(),
                         ancestor=subprocess.run(["git", "merge-base", "--is-ancestor", green_sha, "HEAD"],
                                                 cwd=d).returncode == 0)
        r = subprocess.run([BASH, os.path.abspath(SCRIPT)], cwd=d, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
        lines = open(out).read().split()
        os.remove(out)
        return dict(l.split("=", 1) for l in lines)


@unittest.skipUnless(BASH, "bash not on PATH")
class DerivedFlags(unittest.TestCase):
    PATHS = [["hooks/guard.py"], ["hooks/test_guard.py"], ["janitor/sweep.py"], ["hooks/test_config_watch.py"], ["merge/merge.py"],
             ["README.md"], ["skills/ci-hygiene/SKILL.md"], ["bin/ios-ship"], ["lint/layout.json"], ["actions/stamp/stamp.mjs"],
             ["install.ps1"], ["unlisted/new-file.txt"], ["bin/verdict"], ["settings.json"], ["bin/shoot"]]

    def check(self, got):
        for n in DERIVED_FLAGS:
            self.assertIn(n, got, f"output {n} missing: {got}")
        self.assertEqual(got["checks_windows_sweep"], got["checks_windows_rest"], got)
        # PATHS touch neither direct arm, so the both-flags rule is the whole rule for them.
        both = got["code"] == "true" and got["guard"] == "true"
        self.assertEqual(got["checks_guard"], "true" if both else "false", got)

    def test_sweep_flag_follows_rest_and_guard_flag_needs_code_and_guard(self):
        seen = set()
        for paths in self.PATHS:
            for event in ("pull_request", "push"):
                with self.subTest(paths=paths, event=event):
                    got = run(paths, event=event)
                    self.check(got)
                    seen.add((got["checks_windows_rest"], got["checks_guard"]))
        # The sample reaches both ends: everything on, and a docs-only change with everything off.
        self.assertTrue({("true", "true"), ("false", "false")} <= seen, seen)

    def test_unreadable_diff_turns_the_derived_flags_on(self):
        self.check(run(["hooks/guard.py"], base="0" * 40))
        self.assertEqual(run(["hooks/guard.py"], base="0" * 40)["checks_guard"], "true")


# The export suite (skills/waiting-page/test_export_page.py) runs in checks-shoot, which runs only on `shoot`. The walk below
# lists the repo files the suite reaches. Each of them must set `shoot` alone.
EXPORT_SUITE = "skills/waiting-page/test_export_page.py"
# The four folders the suite's modules put on sys.path. A bare module name resolves to a file in one of them, and any other
# name (a stdlib module, a function) resolves to nothing, so the walk counts repo files only.
EXPORT_SUITE_DIRS = ("skills/waiting-page", "lint", "hooks", "janitor")
# Run or read by the suite, never imported, so the walk cannot reach them. lint/layout.json is read at run time by
# lint/layout.py artifacts(), which the export calls.
EXPORT_SUITE_FILES = ("skills/waiting-page/check_designs.mjs", "skills/waiting-page/page.html", "lint/layout.json")


def imported_names(tree):
    """Each module name the tree imports, at any depth: `import a.b`; `from a import b` (`a`, and `a.b` in case `b` is a
    module); a string literal given to importlib.import_module or __import__."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module
            yield from (node.module + "." + alias.name for alias in node.names)
        elif isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant) \
                and isinstance(node.args[0].value, str):
            fn = node.func
            if (isinstance(fn, ast.Name) and fn.id == "__import__") or \
                    (isinstance(fn, ast.Attribute) and fn.attr == "import_module"
                     and isinstance(fn.value, ast.Name) and fn.value.id == "importlib"):
                yield node.args[0].value


def repo_module(root, name):
    """The repo file a module name stands for in EXPORT_SUITE_DIRS, or None: a/b.py, or a/b/__init__.py for a package."""
    rel = name.replace(".", "/")
    for folder in EXPORT_SUITE_DIRS:
        for cand in ("%s/%s.py" % (folder, rel), "%s/%s/__init__.py" % (folder, rel)):
            if os.path.isfile(os.path.join(root, cand)):
                return cand
    return None


def export_suite_files():
    """-> the repo files the export suite reaches, sorted: its import closure from its own file, plus EXPORT_SUITE_FILES."""
    root = os.path.realpath(os.path.join(HERE, ".."))
    found, todo = {EXPORT_SUITE}, [EXPORT_SUITE]
    while todo:
        with open(os.path.join(root, todo.pop()), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for name in imported_names(tree):
            hit = repo_module(root, name)
            if hit and hit not in found:
                found.add(hit)
                todo.append(hit)
    return sorted(found | set(EXPORT_SUITE_FILES))


@unittest.skipUnless(BASH, "bash not on PATH")
class Scope(unittest.TestCase):
    def assertFlags(self, got, want_true=(), want_false=()):
        for n in ALL:
            self.assertIn(n, got, f"output {n} missing: {got}")
        for n in want_true:
            self.assertEqual(got[n], "true", f"{n}: {got}")
        for n in want_false:
            self.assertEqual(got[n], "false", f"{n}: {got}")

    def test_docs_only_pr_turns_every_job_off(self):
        got = run(["README.md", "decisions/some-record.md"])
        self.assertFlags(got, want_false=ALL)

    def test_merge_change_turns_the_merge_job_on(self):
        got = run(["merge/merge.py"])
        self.assertFlags(got, want_true=["checks_windows_merge", "code"])

    def test_guard_change_turns_the_guard_suites_on(self):
        got = run(["hooks/guard.py"])
        self.assertFlags(got, want_true=["checks_windows", "checks_macos", "guard", "sweep", "code"])
        # The selector's test
        # and mutation test also turn `guard` on. Named failure: the guard suite runs in no job.
        for p in ("hooks/test_guard.py", "hooks/mutate_guard.py"):
            with self.subTest(path=p):
                self.assertFlags(run([p]), want_true=["guard"])

    def test_a_merge_change_leaves_a_job_that_never_runs_merge_suites_off(self):
        got = run(["merge/merge.py"])
        self.assertFlags(got, want_false=["pointer_windows", "shell_macos"])

    def test_workflow_or_scope_script_change_runs_everything(self):
        for p in (".github/workflows/checks.yml", ".github/scripts/ci-scope.sh"):
            self.assertFlags(run([p]), want_true=ALL)

    def test_a_test_run_signing_helper_change_runs_everything(self):
        # Every suite loads the helper, so a change to any of its three twins runs every job.
        for p in ("lint/_test_git.py", "lint/_test_git.sh", "lint/_test_git.mjs"):
            with self.subTest(path=p):
                self.assertFlags(run([p]), want_true=ALL + DERIVED_FLAGS)

    def test_unmapped_path_runs_everything(self):
        self.assertFlags(run(["zz-unmapped/blob.bin"]), want_true=ALL)

    def test_unreadable_diff_runs_everything(self):
        bogus = "f" * 40
        self.assertFlags(run(["README.md"], base=bogus), want_true=ALL)
        self.assertFlags(run(["README.md"], base=""), want_true=ALL)

    def test_push_schedule_and_dispatch_run_everything_even_for_docs(self):
        for ev in ("push", "schedule", "workflow_dispatch"):
            self.assertFlags(run(["README.md"], event=ev), want_true=ALL)

    # Map gaps found in review: each path is read by a suite in another job.
    def test_merge_tool_change_turns_on_the_suites_that_load_it(self):
        self.assertFlags(run(["merge/merge.py"]), want_true=["checks_windows", "checks_macos", "guard", "checks_windows_merge"])

    def test_layout_change_turns_on_the_guard_and_merge_suites(self):
        for path in ("lint/layout.json", "lint/layout.py"):
            self.assertFlags(run([path]), want_true=["checks_windows", "checks_macos", "guard", "code", "checks_windows_merge"])

    def test_janitor_launcher_change_turns_on_the_install_suite(self):
        # `guard` too: the janitor launcher turns the guard suite on.
        self.assertFlags(run(["bin/claude-janitor"]), want_true=["checks_windows", "shell_macos", "guard"])

    def test_windows_install_test_change_turns_on_the_windows_install_job(self):
        # The file is in the base, so an edit to it is no new file in a landed dir; the job that runs it must start.
        self.assertFlags(run(["hooks/test_install_windows.sh"], existing=["hooks/test_install_windows.sh"]),
                         want_true=["checks_windows", "code"])

    def test_silent_undo_checker_change_turns_on_the_merge_job(self):
        self.assertFlags(run(["lint/check_silent_undo.py"]), want_true=["checks_windows_merge"])

    def test_session_start_change_turns_on_the_unknown_read_contract_job(self):
        self.assertFlags(run(["hooks/session_start.sh"]), want_true=["checks_windows_rest"])

    def test_a_new_file_in_a_landed_dir_turns_on_the_install_suite(self):
        for p in ("agents/new.md", "skills/new/SKILL.md", "output-styles/new.md", "lint/new.py"):
            self.assertFlags(run([p]), want_true=["checks_windows", "shell_macos"])
        # Named failure: review
        # finding on #305. The guard suite reads this path; if `guard` stays off, cut F runs it in no job.
        self.assertFlags(run(["lint/zz_new.py"]), want_true=["guard"])

    def test_a_modified_md_under_skills_turns_on_nothing(self):
        self.assertFlags(run(["skills/old/SKILL.md"], existing=["skills/old/SKILL.md"]), want_false=ALL)

    def test_a_new_file_in_hooks_or_janitor_turns_on_the_install_suite(self):
        for p in ("hooks/new.py", "janitor/new.py"):
            self.assertFlags(run([p]), want_true=["checks_windows", "shell_macos"])

    def test_the_landed_dirs_come_from_landed_dirs_txt(self):
        # A made-up dir in the scratch repo's landed-dirs.txt: the script reads the file, it does not copy the list.
        self.assertFlags(run(["zz-made-up/new.md"], landed=["zz-made-up"]), want_true=["checks_windows", "shell_macos"])

    def test_an_empty_or_comment_only_landed_list_turns_everything_on(self):
        for landed in ([], ["# only a comment", ""]):
            self.assertFlags(run(["docs/new.md"], landed=landed), want_true=ALL)

    def test_a_trailing_slash_in_landed_dirs_is_read_as_the_dir(self):
        self.assertFlags(run(["zz-made-up/new.md"], landed=["zz-made-up/"]), want_true=["checks_windows", "shell_macos"])

    # Cut F: checks-windows-guard and checks-mutate-guard skip on the `guard` flag. The slice selector
    # (GUARD_TESTS) is read from hooks/test_guard.py, so an edit to that file must turn `guard` on,
    # or a pull request that changes the slice would run no guard job at all.
    # Control: a docs-only path must keep `guard` off, or the new rules over-trigger (false red).
    def test_a_docs_only_path_keeps_the_guard_flag_off(self):
        for p in ("README.md", "decisions/some-record.md"):
            self.assertFlags(run([p]), want_false=["guard"])

    # lint/guard_log_report.py imports hooks/guard_core.py at load, and decision_watch
    # reads guard.log through it at run time. So a change to it must select the same jobs as
    # lint/_transcript.py, the other module the decision watch loads (the rules at its line 36, 51).
    def test_guard_log_reader_change_selects_the_jobs_of_the_transcript_reader(self):
        reader = self.true_set(run(["lint/guard_log_report.py"]))
        self.assertEqual(reader, self.true_set(run(["lint/_transcript.py"])))
        self.assertTrue({"checks_windows_rest", "checks_macos", "code", "guard"} <= reader, reader)

    # lint/_clause.py: report_guard.py imports it, and test_clause.py is its suite. It sits in the hooks/* arm of ci-scope.sh,
    # so an edit turns on that arm's jobs and no merge job (only the transcript reader and guard_log_report.py reach that one).
    # An edit, not a new file: a new file under lint/ also turns on the landed-dir jobs, which is another arm's rule.
    def test_clause_parser_change_selects_the_jobs_the_arm_names(self):
        self.assertEqual(self.true_set(run(["lint/_clause.py"], existing=["lint/_clause.py"])),
                         {"checks_windows_rest", "checks_macos", "code", "guard", "shoot"},
                         "lint/_clause.py must select the hooks/* arm's jobs and no merge job")

    # Guard family: hooks/guard_<anything>.py is split out of hooks/guard.py. Each sibling must set
    # exactly the flags guard.py sets, as a new file and as an edit. Today the generic hooks/* rule
    # gives a new sibling no sweep flag, and an edited one no Windows or shell job.
    GUARD_SIBLINGS = ["hooks/guard_core.py", "hooks/guard_merge.py", "hooks/guard_rules.py"]

    def true_set(self, got):
        return {n for n in ALL if got[n] == "true"}

    def test_guard_sibling_new_file_sets_the_same_flags_as_guard_py(self):
        want = run(["hooks/guard.py"])
        self.assertFlags(want, want_true=["checks_windows", "checks_windows_rest", "checks_macos", "code", "guard", "sweep"],
                         want_false=["checks_windows_merge", "pointer_windows"])
        for p in self.GUARD_SIBLINGS:
            with self.subTest(path=p):
                self.assertEqual(run([p]), want)

    def test_guard_sibling_edit_sets_the_same_flags_as_guard_py(self):
        want = run(["hooks/guard.py"], existing=["hooks/guard.py"])
        self.assertFlags(want, want_true=["checks_windows", "checks_windows_rest", "checks_macos", "code", "guard", "sweep"],
                         want_false=["checks_windows_merge", "shell_macos", "pointer_windows"])
        for p in self.GUARD_SIBLINGS:
            with self.subTest(path=p):
                self.assertEqual(run([p], existing=[p]), want)

    def test_shared_names_change_sets_the_same_flags_as_guard_py(self):
        # guard_core.py and config_watch.py import it, so the guard mutation tests must run on it.
        want = run(["hooks/guard.py"])
        self.assertEqual(run(["hooks/shared_names.py"]), want)
        self.assertEqual(run(["hooks/shared_names.py"], existing=["hooks/shared_names.py"]),
                         run(["hooks/guard.py"], existing=["hooks/guard.py"]))

    def test_git_reads_change_sets_the_same_flags_as_guard_py(self):
        # guard_core.py and the janitor's sweep.py and session_end_sweep.py import it, so the guard
        # and sweep mutation tests must run on it.
        want = run(["hooks/guard.py"])
        self.assertEqual(run(["hooks/git_reads.py"]), want)
        self.assertEqual(run(["hooks/git_reads.py"], existing=["hooks/git_reads.py"]),
                         run(["hooks/guard.py"], existing=["hooks/guard.py"]))

    # hooks/override.py, hooks/_nowindow.py, hooks/proc_env.py and hooks/reread_check.py load in the guard set (the guard
    # arm of ci-scope.sh lists all four), so a change to any runs the Windows job and the sweep job, as a change to
    # guard.py does. Each path is a new file and an edit.
    def test_guard_set_module_change_turns_on_the_windows_and_sweep_jobs(self):
        for p in ("hooks/override.py", "hooks/_nowindow.py", "hooks/proc_env.py", "hooks/reread_check.py"):
            for existing in ([], [p]):
                with self.subTest(path=p, edit=bool(existing)):
                    self.assertFlags(run([p], existing=existing),
                                     want_true=["checks_windows", "checks_windows_sweep"])

    # Control: the guard test file keeps today's flags. A family rule must not catch it.
    def test_guard_test_file_keeps_its_current_flags(self):
        p = "hooks/guard_test_x.py"
        self.assertEqual(self.true_set(run([p])),
                         {"checks_windows", "checks_windows_rest", "checks_macos", "shell_macos", "code", "guard"})
        self.assertEqual(self.true_set(run([p], existing=[p])), {"checks_windows_rest", "checks_macos", "code", "guard"})

    # Control: the guard selector test keeps today's flags.
    def test_test_guard_keeps_its_current_flags(self):
        p = "hooks/test_guard.py"
        self.assertEqual(self.true_set(run([p])), {"checks_windows", "checks_macos", "shell_macos", "code", "guard"})
        self.assertEqual(self.true_set(run([p], existing=[p])), {"checks_windows", "checks_macos", "code", "guard"})

    # A section file of the guard suite is a part of hooks/test_guard.py, so it sets that suite's flags. It is not
    # under hooks/, so the new-file rule that adds shell_macos for hooks/ does not reach it.
    SECTION_FILE = "tests/guard/s00442-misc.py"

    def test_guard_section_file_sets_the_flags_of_test_guard_not_shell_macos(self):
        want = self.true_set(run(["hooks/test_guard.py"], existing=["hooks/test_guard.py"]))
        self.assertEqual(want, {"checks_windows", "checks_macos", "code", "guard"})
        self.assertEqual(self.true_set(run([self.SECTION_FILE])), want,
                         "a new section file sets flags other than hooks/test_guard.py's")
        self.assertEqual(self.true_set(run([self.SECTION_FILE], existing=[self.SECTION_FILE])), want,
                         "an edited section file sets flags other than hooks/test_guard.py's")

    # Mod and map-skill tests run as a step of the checks, checks-windows and checks-macos jobs, run only on the
    # `mods` flag. A job runs on its own flag, so a path that turns on `mods` must turn on checks_windows and
    # checks_macos too, or a mod-only pull request starts neither job and the step never runs there.
    # `mods` is in ALL, so every fail-safe case in the Scope class carries the mods check.
    MOD_JOBS = ["checks_windows", "checks_macos"]
    def test_a_mods_path_sets_the_mods_flag(self):
        for p in ("mods/plain-diff/check.mjs", "mods/session-board/session-board.test.mjs"):
            with self.subTest(path=p):
                self.assertEqual(run([p]).get("mods"), "true")
        self.assertEqual(run(["README.md", "mods/plain-diff/check.mjs"]).get("mods"), "true")

    def test_a_mods_only_diff_sets_the_mod_jobs_and_no_other_flag(self):
        got = run(["mods/plain-diff/check.mjs"])
        self.assertFlags(got, want_true=["mods"] + self.MOD_JOBS,
                         want_false=[n for n in ALL if n not in ["mods"] + self.MOD_JOBS])

    def test_a_docs_only_diff_leaves_the_mods_flag_off(self):
        self.assertEqual(run(["README.md", "decisions/some-record.md"]).get("mods"), "false")

    # mods/decision-watch/decision-watch.test.mjs imports lint/test_scanner_traps.mjs,
    # and the mod-tests.sh step runs that test. The lint/* rule sets `code` only, so a diff naming only the lint
    # file would skip its test.
    def test_a_scanner_trap_lint_change_sets_the_mods_flag(self):
        self.assertFlags(run(["lint/test_scanner_traps.mjs"]), want_true=["mods", "code"] + self.MOD_JOBS)

    # Each arm that turns `mods` on starts both mod jobs, as a new file and as an edit. An edit leaves every
    # other job flag off, so the set is exact. A new file under lint/ or skills/ is in a landed dir, which adds
    # shell_macos and guard by its own rule, so a new file is checked for the jobs it must not start.
    # `.gitignore` is an arm too: skills/plain-english-map/tests/typescript-home.test.mjs reads it, so a .gitignore-only
    # pull request must run the CI step. It keeps `code`, which its lint suites read.
    MOD_ARMS = ["mods/zz-new/a.mjs", "lint/test_scanner_traps.mjs", "skills/plain-english-map/README.md", ".gitignore"]

    def test_each_mods_arm_starts_the_windows_and_macos_jobs(self):
        for p in self.MOD_ARMS:
            with self.subTest(path=p, edit=True):
                code_arm = p.startswith("lint/") or p == ".gitignore"
                want = {"mods", "checks_windows", "checks_macos"} | ({"code"} if code_arm else set())
                self.assertEqual(self.true_set(run([p], existing=[p])), want,
                                 msg=f"{p}: the mods arm must start the CI step and both mod jobs, and keep code")
            with self.subTest(path=p, edit=False):
                self.assertFlags(run([p]), want_true=["mods"] + self.MOD_JOBS,
                                 want_false=["checks_windows_merge", "checks_windows_rest", "pointer_windows"])

    # Any path under the map skill turns `mods` on, .md files included, as a new file or an edit.
    # The checks job runs the skill's tests only when `mods` is on. Those tests read SKILL.md and
    # .md fixtures, so a .md path with no flag would skip them. The skill and its tests live in
    # this repo (ruling `map-skill-lives-here`: the tests run in the checks workflow).
    MAP_SKILL = "skills/plain-english-map/"

    def test_a_map_skill_md_change_turns_on_mods(self):
        for p in (self.MAP_SKILL + "SKILL.md", self.MAP_SKILL + "tests/fixture/docs/map/core.md",
                  self.MAP_SKILL + "tests/fixture/docs/map/traces/home.md"):
            for existing in ((), (p,)):
                with self.subTest(path=p, edit=bool(existing)):
                    got = run([p], existing=existing)
                    self.assertFlags(got, want_true=["mods"] + self.MOD_JOBS)

    # Control: the fix must not narrow the skill's non-.md paths. They stay on the fail-safe arm.
    def test_a_map_skill_script_change_still_turns_everything_on(self):
        p = self.MAP_SKILL + "scripts/map-check.mjs"
        for existing in ((), (p,)):
            with self.subTest(edit=bool(existing)):
                self.assertFlags(run([p], existing=existing), want_true=ALL)

    # Control: another skill's .md keeps today's flags. The new rule must name the map skill only.
    def test_another_skills_md_keeps_its_current_flags(self):
        p = "skills/ci-hygiene/SKILL.md"
        self.assertFlags(run([p], existing=[p]), want_false=ALL)
        self.assertEqual(self.true_set(run([p])), {"checks_windows", "shell_macos", "code", "guard"})

    # The rm shim suite also runs in checks-macos: BSD rm and the /var symlink change what the shim reads,
    # and a Linux pass proves neither. ci-scope.sh maps bin/rm and the suite to that job ahead of
    # the lint/* rule, which sets `code` only, so a diff that names the suite alone still reaches it.
    def test_an_rm_shim_suite_change_turns_on_the_macos_job(self):
        self.assertFlags(run(["lint/test_rm_shim.py"], existing=["lint/test_rm_shim.py"]), want_true=["checks_macos", "code"])

    # bin/ios-ship and its suite run in the shell-macos job only (macOS /bin/bash 3.2). An edit to either turns on that
    # job and `code`, and no other flag. Without the arm, an unmapped path turns every flag on, so this goes red.
    # Only the edit is exact: a new file under bin/ also sets the install-suite flags (the landed-dirs rule).
    def test_ios_ship_edit_turns_on_only_the_macos_shell_job(self):
        for p in ("bin/ios-ship", "lint/test_ios_ship.sh"):
            with self.subTest(path=p):
                self.assertEqual(self.true_set(run([p], existing=[p])), {"shell_macos", "code"})

    # bin/sim-test and its suite run in the shell-macos job only, like bin/ios-ship. The suite runs the real bin/sim-lease
    # beside the script, so an edit to bin/sim-lease turns the same job on.
    def test_sim_test_edit_turns_on_only_the_macos_shell_job(self):
        for p in ("bin/sim-test", "lint/test_sim_test.sh", "bin/sim-lease"):
            with self.subTest(path=p):
                self.assertEqual(self.true_set(run([p], existing=[p])), {"shell_macos", "code"})

    # bin/duo-fold and its suite run in the shell-macos job only, like bin/sim-test (bash 3.2 on macOS).
    # Named failure: without the arm, bin/duo-fold turns every flag on, and the suite turns on `code` alone.
    def test_duo_fold_edit_turns_on_only_the_macos_shell_job(self):
        for p in ("bin/duo-fold", "lint/test_duo_fold.sh"):
            with self.subTest(path=p):
                self.assertEqual(self.true_set(run([p], existing=[p])), {"shell_macos", "code"})

    # bin/shoot's suite installs a browser, so its own paths and the browser installers turn `shoot` on. An edit sets
    # `code` and `shoot` and no other flag in true_set (checks_guard is outside ALL; the cases below pin it).
    # An unrelated code change leaves `shoot` off.
    def test_shoot_edit_turns_on_only_the_shoot_suite(self):
        for p in ("bin/shoot", "lint/test_shoot.mjs", "testing/skip-locally-fail-in-ci.mjs", ".github/shoot/package-lock.json",
                  "actions/playwright-setup/action.yml"):
            with self.subTest(path=p):
                self.assertEqual(self.true_set(run([p], existing=[p])), {"code", "shoot"})
        self.assertFlags(run(["lint/test_verdict.py"], existing=["lint/test_verdict.py"]), want_false=["shoot"])

    # The waiting page export suite (skills/waiting-page/test_export_page.py) runs in checks-shoot, which runs only on `shoot`.
    # It reads these paths: hooks/question_form.py and hooks/_nowindow.py (through page_check.py), lint/_test_temp.py
    # (its run folder), and the steps it reads, in SKILL.md and in reference/copies-and-accounts.md and reference/repo-pages.md.
    # Every reference/*.md is read by the page suite (skills/waiting-page/tests/page.test.mjs), whose job is conditioned on `shoot` too.
    # Named failure: a PR that changes only one of them leaves `shoot` off, so the suite is skipped.
    def test_waiting_page_export_suite_paths_turn_on_shoot(self):
        for p in ("hooks/question_form.py", "hooks/_nowindow.py", "lint/_test_temp.py", "skills/waiting-page/SKILL.md",
                  "skills/waiting-page/reference/copies-and-accounts.md", "skills/waiting-page/reference/repo-pages.md",
                  "skills/waiting-page/reference/designs.md", "skills/waiting-page/reference/republish.md",
                  "skills/waiting-page/reference/routing-and-sessions.md"):
            with self.subTest(path=p):
                self.assertFlags(run([p], existing=[p]), want_true=["shoot"])

    # Control: the same paths keep the flags they set today, and a sibling in the same arm keeps `shoot` off.
    # Named failure: a fix that moves a path into a new arm, or widens an arm, drops a flag or turns `shoot` on for a sibling.
    def test_waiting_page_export_paths_keep_their_flags_and_their_siblings_keep_shoot_off(self):
        for p, flags in (("hooks/question_form.py", ["code", "guard"]), ("hooks/_nowindow.py", ["code", "guard"]),
                         ("lint/_test_temp.py", ["code"])):
            with self.subTest(path=p):
                self.assertFlags(run([p], existing=[p]), want_true=flags)
        for p in ("hooks/mutate_shared.py", "hooks/config_watch.py"):
            with self.subTest(path=p):
                self.assertFlags(run([p], existing=[p]), want_false=["shoot"])

    # Named failure: a file the suite reaches sets `shoot` off, so a pull request that changes only that file skips the suite.
    # The scope asserts come first. Named failure: a walk that reaches too little passes every file below and proves nothing.
    def test_every_file_the_export_suite_reaches_sets_shoot_alone(self):
        reached = export_suite_files()
        for want in ("skills/waiting-page/export_page.py", "skills/waiting-page/page_check.py", "lint/_test_temp.py",
                     "hooks/_nowindow.py", "janitor/sweep.py") + EXPORT_SUITE_FILES:
            self.assertIn(want, reached, "the export suite's walk does not reach %s" % want)
        # The sibling control above pins these two with `shoot` off, so the walk must not reach them.
        for not_want in ("hooks/mutate_shared.py", "hooks/config_watch.py"):
            self.assertNotIn(not_want, reached,
                             "the export suite's walk reaches %s, which the sibling control pins off" % not_want)
        missing = [p for p in reached if run([p], existing=[p]).get("shoot") != "true"]
        if missing:
            self.fail("shoot stays off when a pull request changes only one of these export suite files, "
                      "so the suite is skipped:\n  " + "\n  ".join(missing))

    # actions/playwright-setup has four callers (checks.yml): checks-guard and checks-guard-2 are conditioned on checks_guard
    # alone, and checks-shoot and checks-waiting-page are conditioned on shoot alone. An edit to the action must set
    # checks_guard directly, with `shoot` for the two shoot jobs.
    # Named failure: the action arm sets code and shoot only, so checks-guard skips its install and guard suite.
    def test_playwright_action_edit_turns_on_the_checks_guard_job(self):
        p = "actions/playwright-setup/action.yml"
        got = run([p], existing=[p])
        self.assertFlags(got, want_true=["code", "shoot"])
        self.assertIn("checks_guard", got, got)
        self.assertEqual(got["checks_guard"], "true", f"checks_guard: {got}")

    # Control: a bin/shoot edit keeps checks_guard off, so the action's arm must not widen to bin/shoot.
    def test_shoot_edit_keeps_checks_guard_off(self):
        p = "bin/shoot"
        got = run([p], existing=[p])
        self.assertFlags(got, want_true=["code", "shoot"])
        self.assertIn("checks_guard", got, got)
        self.assertEqual(got["checks_guard"], "false", f"checks_guard: {got}")

    # checks-guard installs the Playwright that .github/shoot pins, so a change to that pin must start the job.
    # Named failure: the pin path sets code and shoot only, and checks-guard installs the old browser.
    def test_shoot_package_lock_edit_turns_on_the_checks_guard_job(self):
        p = ".github/shoot/package-lock.json"
        got = run([p], existing=[p])
        self.assertFlags(got, want_true=["code", "shoot"])
        self.assertIn("checks_guard", got, got)
        self.assertEqual(got["checks_guard"], "true", f"checks_guard: {got}")

    # pin.sh is the install script checks-guard runs from actions/playwright-setup. Named failure: an edit that
    # starts the shoot jobs and no checks-guard job leaves the checks-guard install on the old script.
    def test_playwright_pin_script_edit_turns_on_the_checks_guard_job(self):
        p = "actions/playwright-setup/pin.sh"
        got = run([p], existing=[p])
        self.assertFlags(got, want_true=["code", "shoot"])
        self.assertIn("checks_guard", got, got)
        self.assertEqual(got["checks_guard"], "true", f"checks_guard: {got}")

    # A .md edit under the action is docs, so no caller starts. Named failure: without the *.md carve-out, the
    # action arm starts the two shoot jobs and the two checks-guard jobs for a README edit.
    def test_playwright_readme_edit_turns_on_no_job(self):
        p = "actions/playwright-setup/README.md"
        got = run([p], existing=[p])
        self.assertFlags(got, want_false=["code", "shoot"])
        self.assertIn("checks_guard", got, got)
        self.assertEqual(got["checks_guard"], "false", f"checks_guard: {got}")


# A records-only push after a fully green head. GREEN_HEAD names the
# pull request's newest earlier head whose `checks` run was fully green. When the delta from it to HEAD is docs/records.md
# alone, the 13 job and suite flags below are false, and so is mutation_report: the shortcut skips every job of the push.
# The four lint flags keep their whole-PR values. Every other case runs as before: the flags follow the whole PR diff
# against BASE_SHA.
def differing(got, want, names=None):
    """-> the sorted names whose value in `got` is not `want`'s. Default: every name either one holds."""
    names = set(got) | set(want) if names is None else names
    return sorted(n for n in names if got.get(n) != want.get(n))


@unittest.skipUnless(BASH, "bash not on PATH")
class RecordsOnlyPush(unittest.TestCase):
    CODE = ["hooks/guard.py"]  # the whole PR diff holds a code file, so the whole-PR result turns the jobs on
    RECORDS = "docs/records.md"
    OFF = JOB_FLAGS + STEP_FLAGS + DERIVED_FLAGS  # the 13 flags a records-only push after a green head turns off
    ABSENT_SHA = "0123456789abcdef0123456789abcdef01234567"  # a sha no scratch repo holds
    BASE_CHANGE = "janitor/sweep.py"  # a base change the merge commit brings in, never in the pull request's own diff

    def whole_pr(self, paths, contents=None, landed=None):
        """The whole PR diff: `paths` in one head commit, with GREEN_HEAD empty. `landed` is run()'s landed-dirs list."""
        return run(paths, contents=contents, landed=landed)

    def assertSkipFlag(self, got, skipped):
        """records_only_skip is 'true' when the shortcut forced the 13 flags off, and 'false' in every other case."""
        self.assertIn("records_only_skip", got, f"ci-scope.sh writes no records_only_skip line: {got}")
        want = "true" if skipped else "false"
        self.assertEqual(got["records_only_skip"], want, f"records_only_skip is {got['records_only_skip']}, want {want}: {got}")

    # A sibling GREEN_HEAD is not an earlier head of HEAD. Its tree differs from HEAD's by docs/records.md alone, so the
    # delta lists exactly that path, and only the ancestry check tells it apart from a real earlier head. The flags must
    # follow the whole PR diff, never the shortcut.
    def test_records_only_green_head_not_an_ancestor_of_head_runs_everything(self):
        whole = self.whole_pr(self.CODE + [self.RECORDS])
        self.assertEqual(whole.get("code"), "true", f"scope: the whole PR diff must turn code on: {whole}")
        facts = {}
        got = run([self.RECORDS], green=self.CODE, green_sibling=True, facts=facts)
        self.assertEqual(facts.get("delta"), [self.RECORDS],
                         f"scope: the delta from GREEN_HEAD to HEAD is not docs/records.md alone: {facts}")
        self.assertIs(facts.get("ancestor"), False, f"scope: GREEN_HEAD is an ancestor of HEAD: {facts}")
        self.assertEqual(differing(got, whole), [], f"a sibling GREEN_HEAD moved a flag off the whole PR diff: {got}")
        self.assertSkipFlag(got, False)

    def test_records_only_delta_after_green_head_sets_all_13_flags_off(self):
        whole = self.whole_pr(self.CODE + [self.RECORDS])
        self.assertEqual(whole.get("code"), "true", f"scope: the whole PR diff must turn code on: {whole}")
        facts = {}
        got = run([self.RECORDS], green=self.CODE, facts=facts)
        self.assertEqual(facts.get("delta"), [self.RECORDS],
                         f"scope: the delta from GREEN_HEAD to HEAD is not docs/records.md alone: {facts}")
        self.assertIs(facts.get("ancestor"), True, f"scope: GREEN_HEAD is not an earlier head of HEAD: {facts}")
        for n in self.OFF:
            self.assertEqual(got.get(n), "false", f"{n} stays on after a records-only push past a green head: {got}")
        keep = list(LINT_FLAGS)
        self.assertEqual(differing(got, whole, keep), [], f"a lint flag moved off the whole PR diff: {got}")

    # The skip flag is 'true' exactly when the shortcut forced the 13 flags off. In CI HEAD is the merge commit, so the merged
    # shape is checked too. The facts are read before the flags and the flag (P7).
    def test_records_only_skip_flag_is_true_when_the_shortcut_forces_the_flags_off(self):
        for merged in (None, [self.BASE_CHANGE]):
            with self.subTest(merged=merged):
                facts = {}
                got = run([self.RECORDS], green=self.CODE, merged=merged, facts=facts)
                self.assertIs(facts.get("ancestor"), True, f"scope: GREEN_HEAD is not an earlier head of HEAD: {facts}")
                self.assertEqual(facts.get("delta_pr_head"), [self.RECORDS],
                                 f"scope: the delta to PR_HEAD is not docs/records.md alone: {facts}")
                for n in self.OFF:
                    self.assertEqual(got.get(n), "false", f"{n} stays on after a records-only push past a green head: {got}")
                self.assertSkipFlag(got, True)

    # GREEN_HEAD empty: the earlier head is unknown or its run was red. The whole PR diff decides, as before.
    def test_records_only_green_head_empty_runs_as_before(self):
        whole = self.whole_pr(self.CODE + [self.RECORDS])
        self.assertEqual(whole.get("code"), "true", f"scope: the whole PR diff must turn code on: {whole}")
        facts = {}
        got = run([self.RECORDS], green=self.CODE, green_head="", facts=facts)
        self.assertEqual(facts.get("delta"), [self.RECORDS], f"scope: the delta is not docs/records.md alone: {facts}")
        self.assertEqual(differing(got, whole), [], f"an empty GREEN_HEAD moved a flag off the whole PR diff: {got}")
        self.assertSkipFlag(got, False)

    # GREEN_HEAD names a sha the repo lacks: git cannot read the delta from it, so the whole PR diff decides. Never green.
    def test_records_only_green_head_absent_from_repo_runs_as_before(self):
        whole = self.whole_pr(self.CODE + [self.RECORDS])
        self.assertEqual(whole.get("code"), "true", f"scope: the whole PR diff must turn code on: {whole}")
        facts = {}
        got = run([self.RECORDS], green=self.CODE, green_head=self.ABSENT_SHA, facts=facts)
        self.assertEqual(facts.get("delta"), [self.RECORDS], f"scope: the real earlier head's delta is not records only: {facts}")
        self.assertEqual(differing(got, whole), [], f"an absent GREEN_HEAD moved a flag off the whole PR diff: {got}")
        self.assertSkipFlag(got, False)

    # An empty landed-dirs.txt is the fail-safe: every flag is on. The shortcut's inputs all hold here (GREEN_HEAD is an earlier
    # head and the delta is docs/records.md alone), so only the fail-safe keeps the flags on. The whole PR diff is read with
    # the same empty list.
    def test_records_only_empty_landed_dirs_list_runs_everything(self):
        whole = self.whole_pr(self.CODE + [self.RECORDS], landed=[])
        self.assertEqual(whole.get("code"), "true", f"scope: the whole PR diff must turn code on: {whole}")
        facts = {}
        got = run([self.RECORDS], green=self.CODE, landed=[], facts=facts)
        self.assertIs(facts.get("ancestor"), True, f"scope: GREEN_HEAD is not an earlier head of HEAD: {facts}")
        self.assertEqual(facts.get("delta"), [self.RECORDS],
                         f"scope: the delta from GREEN_HEAD to HEAD is not docs/records.md alone: {facts}")
        self.assertSkipFlag(got, False)
        for n in self.OFF:
            self.assertEqual(got.get(n), "true", f"{n} is off with an empty landed-dirs list, so the fail-safe did not set it: {got}")
        self.assertEqual(differing(got, whole), [], f"an empty landed-dirs list moved a flag off the whole PR diff: {got}")

    # Only docs/records.md skips. The delta must be exactly that path, so a second path, of any kind, runs the whole PR diff.
    def test_records_only_delta_with_one_other_path_runs_as_before(self):
        for other in ("README.md", "hooks/extra.py"):
            with self.subTest(other=other):
                whole = self.whole_pr(self.CODE + [self.RECORDS, other])
                self.assertEqual(whole.get("code"), "true", f"scope: the whole PR diff must turn code on: {whole}")
                facts = {}
                got = run([self.RECORDS, other], green=self.CODE, facts=facts)
                self.assertEqual(facts.get("delta"), sorted([self.RECORDS, other]), f"scope: the delta is not the two paths: {facts}")
                self.assertEqual(differing(got, whole), [], f"a second delta path moved a flag off the whole PR diff: {got}")
                self.assertSkipFlag(got, False)

    # The script judges no page content: the `checks` job runs hook_catalog.py --check on the page. So a hand-edited records
    # page skips the same jobs as a generated one, and the lint flags keep their whole-PR values.
    def test_records_only_hand_edited_page_turns_the_jobs_off_and_keeps_lint_flags(self):
        hand = {self.RECORDS: "# Records\n\nHand-edited, not a generated page.\n"}
        whole = self.whole_pr(self.CODE + [self.RECORDS], contents=hand)
        self.assertEqual(whole.get("code"), "true", f"scope: the whole PR diff must turn code on: {whole}")
        facts = {}
        got = run([self.RECORDS], green=self.CODE, contents=hand, facts=facts)
        self.assertEqual(facts.get("delta"), [self.RECORDS], f"scope: the delta is not docs/records.md alone: {facts}")
        for n in self.OFF:
            self.assertEqual(got.get(n), "false", f"{n} stays on for a hand-edited records page: {got}")
        keep = list(LINT_FLAGS)
        self.assertEqual(differing(got, whole, keep), [], f"a lint flag moved for a hand-edited page: {got}")

    # A push past a fully green head skips the same 13 flags as a pull request. Ruling 830 c (every job on a records-only
    # push after a green head), widened by item 857 pick b (19:48 CST Nov 15). Named failure: a records-only push keeps a job
    # flag on, so its job still runs.
    # The delta is asserted before the flags (P7).
    def test_records_only_push_after_green_head_turns_the_jobs_off(self):
        facts = {}
        got = run([self.RECORDS], green=self.CODE, event="push", facts=facts)
        self.assertIs(facts.get("ancestor"), True, f"scope: GREEN_HEAD is not an earlier head of HEAD: {facts}")
        self.assertEqual(facts.get("delta"), [self.RECORDS], f"scope: the delta is not docs/records.md alone: {facts}")
        for n in self.OFF:
            self.assertEqual(got.get(n), "false", f"{n} stays on after a records-only push past a green head: {got}")
        self.assertSkipFlag(got, True)

    # An empty delta (no commit past GREEN_HEAD) is not records-only, so the whole PR diff decides.
    def test_records_only_empty_delta_runs_as_before(self):
        whole = self.whole_pr(self.CODE)
        self.assertEqual(whole.get("code"), "true", f"scope: the whole PR diff must turn code on: {whole}")
        facts = {}
        got = run([], green=self.CODE, facts=facts)
        self.assertEqual(facts.get("delta"), [], f"scope: the delta from GREEN_HEAD to HEAD is not empty: {facts}")
        self.assertEqual(differing(got, whole), [], f"an empty delta moved a flag off the whole PR diff: {got}")
        self.assertSkipFlag(got, False)

    # Another docs page alone after a green head is not docs/records.md, so it runs the whole PR diff, as before.
    def test_records_only_other_docs_page_alone_runs_as_before(self):
        other = "docs/notes.md"
        whole = self.whole_pr(self.CODE + [other])
        self.assertEqual(whole.get("code"), "true", f"scope: the whole PR diff must turn code on: {whole}")
        facts = {}
        got = run([other], green=self.CODE, facts=facts)
        self.assertEqual(facts.get("delta"), [other], f"scope: the delta is not the one docs page: {facts}")
        self.assertEqual(differing(got, whole), [], f"a docs page other than records moved a flag: {got}")
        self.assertSkipFlag(got, False)

    # In CI HEAD is the merge commit, which also holds a base change the pull request did not make. The delta must run to
    # PR_HEAD, the pull request's own head, or that base change keeps the jobs on. The delta is asserted before the flags.
    def test_records_only_uses_pr_head_not_the_merge_commit_skips_the_jobs(self):
        whole = self.whole_pr(self.CODE + [self.RECORDS])
        self.assertEqual(whole.get("code"), "true", f"scope: the whole PR diff must turn code on: {whole}")
        facts = {}
        got = run([self.RECORDS], green=self.CODE, merged=[self.BASE_CHANGE], facts=facts)
        self.assertNotEqual(facts.get("delta_head"), [self.RECORDS],
                            f"scope: the delta to the merge commit is records only, so the base change is not in it: {facts}")
        self.assertEqual(facts.get("delta_pr_head"), [self.RECORDS],
                         f"scope: the delta to PR_HEAD is not docs/records.md alone: {facts}")
        for n in self.OFF:
            self.assertEqual(got.get(n), "false", f"{n} stays on: the delta ran to the merge commit, not PR_HEAD: {got}")
        keep = list(LINT_FLAGS)
        self.assertEqual(differing(got, whole, keep), [], f"a lint flag moved off the whole PR diff: {got}")

    # The control beside the case above: a second delta path runs the whole PR diff, with the base change in the merge commit too.
    def test_records_only_uses_pr_head_not_the_merge_commit_second_path_runs_as_before(self):
        other = "hooks/extra.py"
        whole = self.whole_pr(self.CODE + [self.RECORDS, other])
        self.assertEqual(whole.get("code"), "true", f"scope: the whole PR diff must turn code on: {whole}")
        facts = {}
        got = run([self.RECORDS, other], green=self.CODE, merged=[self.BASE_CHANGE], facts=facts)
        self.assertEqual(facts.get("delta_pr_head"), sorted([self.RECORDS, other]), f"scope: the delta to PR_HEAD is not the two paths: {facts}")
        self.assertEqual(differing(got, whole), [], f"a second delta path moved a flag off the whole PR diff: {got}")
        self.assertSkipFlag(got, False)

    # The shortcut turns off every job of a records-only push, the mutation-report job included, whatever the head ref.
    # The scope is asserted before the flag (P7): the shortcut applies, then mutation_report is read.
    def test_records_only_mutation_report_skip_applies_integration_branch_is_false(self):
        facts = {}
        got = run([self.RECORDS], green=self.CODE, head_ref="batch-x", facts=facts)
        self.assertIs(facts.get("ancestor"), True, f"scope: GREEN_HEAD is not an earlier head of HEAD: {facts}")
        self.assertEqual(facts.get("delta"), [self.RECORDS], f"scope: the delta is not docs/records.md alone: {facts}")
        self.assertSkipFlag(got, True)
        self.assertEqual(got.get("mutation_report"), "false", f"a records-only push on a batch pull request turns mutation_report on: {got}")

    # The same shortcut on a pull request from another branch: mutation_report is false, as it was before the shortcut.
    def test_records_only_mutation_report_skip_applies_lane_branch_is_false(self):
        facts = {}
        got = run([self.RECORDS], green=self.CODE, head_ref="lane-x", facts=facts)
        self.assertIs(facts.get("ancestor"), True, f"scope: GREEN_HEAD is not an earlier head of HEAD: {facts}")
        self.assertEqual(facts.get("delta"), [self.RECORDS], f"scope: the delta is not docs/records.md alone: {facts}")
        self.assertSkipFlag(got, True)
        self.assertEqual(got.get("mutation_report"), "false", f"a records-only push on a lane pull request turns mutation_report on: {got}")

    # The control beside the two cases above: GREEN_HEAD empty, so the shortcut does not apply and a batch pull request keeps
    # mutation_report on. The skip is asserted before the flag (P7).
    def test_records_only_mutation_report_skip_does_not_apply_integration_branch_is_true(self):
        facts = {}
        got = run([self.RECORDS], green=self.CODE, green_head="", head_ref="batch-x", facts=facts)
        self.assertEqual(facts.get("delta"), [self.RECORDS], f"scope: the delta is not docs/records.md alone: {facts}")
        self.assertSkipFlag(got, False)
        self.assertEqual(got.get("mutation_report"), "true", f"a batch pull request with no green head turns mutation_report off: {got}")

    # Ruling 830 c, widened by item 857 pick b (19:48 CST Nov 15): a records-only push past a green head turns
    # mutation_report off too. Named failure: the
    # mutation-report job starts on a records-only push. The scope is asserted before the flag (P7).
    def test_records_only_push_after_green_head_turns_mutation_report_off(self):
        facts = {}
        got = run([self.RECORDS], green=self.CODE, event="push", facts=facts)
        self.assertIs(facts.get("ancestor"), True, f"scope: GREEN_HEAD is not an earlier head of HEAD: {facts}")
        self.assertEqual(facts.get("delta"), [self.RECORDS], f"scope: the delta is not docs/records.md alone: {facts}")
        self.assertSkipFlag(got, True)
        self.assertEqual(got.get("mutation_report"), "false", f"a records-only push past a green head turns mutation_report on: {got}")

    # Controls for the wider skip: a push with no earlier green head, or with a second delta path, runs every
    # flag as before. Named failure: the skip reads a GREEN_HEAD or a delta it must not.
    def test_records_only_push_with_no_earlier_green_head_runs_everything(self):
        facts = {}
        got = run([self.RECORDS], green=self.CODE, green_head="", event="push", facts=facts)
        self.assertEqual(facts.get("delta"), [self.RECORDS], f"scope: the delta is not docs/records.md alone: {facts}")
        self.assertSkipFlag(got, False)
        for n in JOB_FLAGS + DERIVED_FLAGS + STEP_FLAGS:
            self.assertEqual(got.get(n), "true", f"a push with no green head runs {n} as before: {got}")
        self.assertEqual(got.get("mutation_report"), "true", f"a push with no green head turns mutation_report off: {got}")

    def test_records_only_push_with_a_second_path_runs_everything(self):
        other = "hooks/extra.py"
        facts = {}
        got = run([self.RECORDS, other], green=self.CODE, event="push", facts=facts)
        self.assertEqual(facts.get("delta"), sorted([self.RECORDS, other]), f"scope: the delta is not the two paths: {facts}")
        self.assertSkipFlag(got, False)
        for n in JOB_FLAGS + DERIVED_FLAGS + STEP_FLAGS:
            self.assertEqual(got.get(n), "true", f"a push with a second delta path runs {n} as before: {got}")

    # A schedule and a dispatch never take the shortcut, whatever the delta and GREEN_HEAD: the nightly run and a manual run keep
    # every job on. Named failure: the wider skip reaches a run that is neither a push nor a pull request.
    def test_records_only_schedule_and_dispatch_run_everything(self):
        for event in ("schedule", "workflow_dispatch"):
            with self.subTest(event=event):
                facts = {}
                got = run([self.RECORDS], green=self.CODE, event=event, facts=facts)
                self.assertEqual(facts.get("delta"), [self.RECORDS], f"scope: the delta is not docs/records.md alone: {facts}")
                self.assertSkipFlag(got, False)
                for n in JOB_FLAGS + DERIVED_FLAGS + STEP_FLAGS:
                    self.assertEqual(got.get(n), "true", f"a {event} run turns {n} off: {got}")


# The job-level half of the wider skip. A job that holds its steps back with a step-level if still starts a runner, so the skip
# is read where a job starts: its job-level if, evaluated on the outputs the scope job wrote for the run. _IfParser reads the
# forms checks.yml's job-level ifs use (names, string literals, ==, !=, !, &&, ||, parentheses, always(), cancelled(),
# success()). Any other text fails the case; it never reads as true.
_IF_TOKEN = re.compile(r"==|!=|&&|\|\||\(|\)|!|'[^']*'|[A-Za-z_][\w.\-]*(?:\(\))?")
_IF_FUNCTIONS = {"always()": True, "cancelled()": False, "success()": True}


def _as_text(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _truthy(value):
    return value if isinstance(value, bool) else _as_text(value) != ""


class _IfParser:
    """Recursive descent over one if: expression, without its ${{ }} wrapper. Precedence as GitHub's: ! binds first, then
    == and !=, then &&, then ||. A name the env does not hold reads as empty, as a missing scope output does."""

    def __init__(self, src, env):
        self.toks = _IF_TOKEN.findall(src)
        if re.sub(r"\s+", "", src) != "".join(self.toks):
            raise ValueError(f"an if: form this reader does not know: {src!r}")
        self.env = env
        self.i = 0

    def peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else None

    def take(self):
        tok = self.peek()
        if tok is None:
            raise ValueError("an if: ends early")
        self.i += 1
        return tok

    def parse(self):
        value = self.disjunction()
        if self.peek() is not None:
            raise ValueError(f"an if: has text after its end: {self.peek()!r}")
        return _truthy(value)

    # Both operands are parsed before they combine: a short-circuit would leave the right side's tokens unread.
    def disjunction(self):
        value = self.conjunction()
        while self.peek() == "||":
            self.take()
            right = self.conjunction()
            value = _truthy(value) or _truthy(right)
        return value

    def conjunction(self):
        value = self.comparison()
        while self.peek() == "&&":
            self.take()
            right = self.comparison()
            value = _truthy(value) and _truthy(right)
        return value

    def comparison(self):
        value = self.unary()
        if self.peek() in ("==", "!="):
            op = self.take()
            same = _as_text(value).lower() == _as_text(self.unary()).lower()
            return same if op == "==" else not same
        return value

    def unary(self):
        if self.peek() == "!":
            self.take()
            return not _truthy(self.unary())
        return self.primary()

    def primary(self):
        tok = self.take()
        if tok == "(":
            value = self.disjunction()
            if self.take() != ")":
                raise ValueError("an if: has an open parenthesis")
            return value
        if tok.startswith("'"):
            return tok[1:-1]
        if tok in _IF_FUNCTIONS:
            return _IF_FUNCTIONS[tok]
        if tok.endswith("()"):
            raise ValueError(f"an if: calls {tok}, which this reader does not know")
        return self.env.get(tok, "")


def if_env(outs, event):
    """The names an if: reads: the event, the pull request's draft flag, and each scope output of the run."""
    env = {"github.event_name": event, "github.event.pull_request.draft": False if event == "pull_request" else None}
    env.update({f"needs.scope.outputs.{name}": value for name, value in outs.items()})
    return env


def job_names(text):
    """The job keys of checks.yml, in file order: the lines under `jobs:` that open a job."""
    return re.findall(r"^  ([A-Za-z0-9_-]+):\s*$", text.split("\njobs:\n", 1)[-1], re.M)


def job_if(text, job):
    """A job's job-level if: expression, without its ${{ }} wrapper. None when the job has no job-level if."""
    m = re.search(r"^    if: (.*)$", job_block(text, job) or "", re.M)
    if m is None:
        return None
    raw = m.group(1).strip()
    wrapped = re.fullmatch(r"\$\{\{(.*)\}\}", raw)
    return (wrapped.group(1) if wrapped else raw).strip()


def job_runs(expr, outs, event):
    """True when the job starts on this run: it has no job-level if, or its if: is true on the run's outputs."""
    return True if expr is None else _IfParser(expr, if_env(outs, event)).parse()


def running_jobs(text, outs, event):
    """The jobs of checks.yml that start on this run, sorted."""
    return sorted(job for job in job_names(text) if job_runs(job_if(text, job), outs, event))


def rollup_needs(text):
    """The jobs all-jobs-passed lists under needs:, in file order."""
    m = re.search(r"^    needs:\n((?:      - [\w-]+\n)+)", job_block(text, "all-jobs-passed") or "", re.M)
    return re.findall(r"^      - ([\w-]+)$", m.group(1), re.M) if m else []


@unittest.skipUnless(BASH, "bash not on PATH")
class RecordsOnlyEveryJob(unittest.TestCase):
    """The wider skip, ruling 830 c widened by item 857 pick b (19:48 CST Nov 15): a records-only run starts no job
    except the decision jobs, which decide or read the skip, and the rollup on a pull request. A step-level skip still starts
    a runner, so each job's job-level if is read on the outputs ci-scope.sh wrote for a real records-only run."""
    RECORDS = RecordsOnlyPush.RECORDS
    CODE = RecordsOnlyPush.CODE
    EARLIER = ["README.md"]  # an earlier head's change that no job reads: a markdown file, not records
    EVENTS = ("pull_request", "push")
    # Decide the skip (scope), or read it on every run (the two skip jobs). The rollup joins them on a pull request only.
    DECISION_JOBS = ("scope", "nightly-skip", "push-skip")
    # A records change beside one of these must start every job the file alone starts.
    CONTROL_EXTRAS = (
        ("a code file", "hooks/extra.py"),
        ("a test file", "lint/test_ci_scope.py"),
        ("a guard file", "hooks/guard.py"),
        ("a workflow file", ".github/workflows/checks.yml"),
        ("the scope script", ".github/scripts/ci-scope.sh"),
    )

    def workflow(self):
        path, why = job_workflow(os.path.join(HERE, ".."), "checks")
        if why:
            self.fail(why)
        with open(path, encoding="utf-8") as f:
            return f.read()

    # Named failure: a job starts on a records-only run. One subtest per job and event, so each job reports its own if:.
    # The delta is asserted before the jobs (P7).
    def test_every_job_but_the_decision_jobs_is_off_on_a_records_only_run(self):
        text = self.workflow()
        self.assertIn("\njobs:\n", text, "checks.yml has no jobs: section")
        jobs = job_names(text)
        self.assertIn("checks", jobs, f"checks.yml names no checks job: {jobs}")
        for event in self.EVENTS:
            with self.subTest(event=event):
                facts = {}
                got = run([self.RECORDS], green=self.CODE, event=event, facts=facts)
                self.assertIs(facts.get("ancestor"), True, f"scope: GREEN_HEAD is not an earlier head of HEAD: {facts}")
                self.assertEqual(facts.get("delta"), [self.RECORDS], f"scope: the delta is not docs/records.md alone: {facts}")
                skip = {*self.DECISION_JOBS, "all-jobs-passed"}
                for job in jobs:
                    if job in skip:
                        continue
                    with self.subTest(job=job):
                        expr = job_if(text, job)
                        self.assertFalse(job_runs(expr, got, event),
                                         f"{job} starts on a records-only {event} run; its job-level if is {expr or 'absent'}")

    # Control: the decision jobs and, on a pull request, the rollup start on a records-only run.
    def test_the_decision_jobs_and_the_rollup_start_on_a_records_only_run(self):
        text = self.workflow()
        for event in self.EVENTS:
            with self.subTest(event=event):
                facts = {}
                got = run([self.RECORDS], green=self.CODE, event=event, facts=facts)
                self.assertIs(facts.get("ancestor"), True, f"scope: GREEN_HEAD is not an earlier head of HEAD: {facts}")
                self.assertEqual(facts.get("delta"), [self.RECORDS], f"scope: the delta is not docs/records.md alone: {facts}")
                jobs = list(self.DECISION_JOBS) + (["all-jobs-passed"] if event == "pull_request" else [])
                for job in jobs:
                    with self.subTest(job=job):
                        expr = job_if(text, job)
                        self.assertTrue(job_runs(expr, got, event),
                                        f"{job} does not start on a records-only {event} run; its job-level if is {expr}")

    # Control: the reader reads the wider skip's form as off when records_only_skip is 'true' and on when it is
    # 'false', and refuses a form it does not know rather than reading it as true.
    def test_the_if_reader_reads_the_records_only_skip_and_refuses_an_unknown_form(self):
        expr = "needs.scope.outputs.records_only_skip != 'true'"
        self.assertFalse(_IfParser(expr, {"needs.scope.outputs.records_only_skip": "true"}).parse(),
                         "the reader reads a records-only skip as on")
        self.assertTrue(_IfParser(expr, {"needs.scope.outputs.records_only_skip": "false"}).parse(),
                        "the reader reads a run with no records-only skip as off")
        with self.assertRaises(ValueError, msg="the reader accepts a form it does not know"):
            _IfParser("github.event_name == 'push' ? 'a' : 'b'", {}).parse()

    # Controls: a records change beside another file starts the jobs that file starts alone, and a workflow
    # change beside records starts every job the rollup needs. The delta is asserted before the jobs (P7).
    def test_a_records_change_beside_another_file_starts_the_jobs_that_file_starts_alone(self):
        text = self.workflow()
        for label, extra in self.CONTROL_EXTRAS:
            with self.subTest(extra=label):
                facts = {}
                got = run([self.RECORDS, extra], green=self.EARLIER, facts=facts)
                self.assertEqual(facts.get("delta"), sorted([self.RECORDS, extra]),
                                 f"scope: the delta is not the records file and {extra}: {facts}")
                self.assertEqual(got.get("records_only_skip"), "false", f"scope: a records change beside {extra} reads as records-only: {got}")
                alone = running_jobs(text, run(self.EARLIER + [self.RECORDS, extra]), "pull_request")
                together = running_jobs(text, got, "pull_request")
                self.assertIn("checks", together, f"the lint job does not start for a records change beside {extra}: {together}")
                self.assertEqual(together, alone, f"a records change beside {extra} starts other jobs than {extra} alone: {together}")
                if extra == ".github/workflows/checks.yml":
                    missing = sorted(set(rollup_needs(text)) - set(together))
                    self.assertEqual(missing, [], f"a workflow change beside records leaves rollup jobs off: {missing}")


# The mod phase must run each mods check script (mods/**/check.mjs), not only *.test.mjs. The script cds to its own
# root, so each case runs a copy of it inside a scratch tree under the run folder.
@unittest.skipUnless(BASH, "bash not on PATH")
class ModTestsRunsEveryCheck(unittest.TestCase):
    SENTINEL = "zz-mod-check-ran"
    # Candidate names for the passing test file. find lists by the filesystem's directory order, which depends on
    # the names, so a case tries these until one lists check.mjs where it needs it.
    TEST_NAMES = ["plain-diff.test.mjs"] + [f"{c}.test.mjs" for c in "abcdefghijklmnop"]

    @classmethod
    def setUpClass(cls):
        cls.run_dir = RUN_DIR

    def setUp(self):
        # In CI a missing node is a red run, never a skip: the mod phase cannot run without it.
        if shutil.which("node") is None:
            if os.environ.get("CI"):
                self.fail("node is not on PATH in CI, so the mod phase cannot run")
            self.skipTest("node not on PATH")

    @staticmethod
    def node_script(exit_code, say=None):
        """A node file that prints `say` to stderr, then exits with `exit_code`."""
        printed = f"console.error({say!r});\n" if say else ""
        return printed + f"process.exit({exit_code});\n"

    def make_tree(self, name, test=None, check=None, test_name="plain-diff.test.mjs"):
        """A scratch tree: mod-tests.sh, one mod test file (passing by default), and mods/plain-diff/check.mjs if `check` is given."""
        tree = os.path.join(self.run_dir, name)
        tracked_tree.copy_tracked(tree, ".github/scripts")
        plain = os.path.join(tree, "mods", "plain-diff")
        os.makedirs(plain)
        with open(os.path.join(plain, test_name), "w") as f:
            f.write(test or self.node_script(0))
        if check is not None:
            with open(os.path.join(plain, "check.mjs"), "w") as f:
                f.write(check)
        return tree

    def run_phase(self, tree):
        """The mods phase of the copied script, run from `tree`, which holds every file the phase can see."""
        return subprocess.run([BASH, os.path.join(tree, ".github", "scripts", "mod-tests.sh"), "mods"],
                              cwd=tree, capture_output=True, text=True)

    def listing(self, tree):
        """The .mjs files under mods/ in the order find lists them. The mod phase lists a subset of these in the same order."""
        r = subprocess.run(["find", "mods", "-type", "f", "-name", "*.mjs"], cwd=tree, capture_output=True, text=True, check=True)
        return r.stdout.split()

    def tree_listing_check(self, name, check_last):
        """A scratch tree with one passing test file and the red check, listed last (check_last) or first."""
        for i, test_name in enumerate(self.TEST_NAMES):
            tree = self.make_tree(f"{name}-{i}", check=self.node_script(1, self.SENTINEL), test_name=test_name)
            listed = self.listing(tree)
            if len(listed) == 2 and listed[-1].endswith("check.mjs") == check_last:
                return tree
        self.fail(f"no candidate test name lists check.mjs {'last' if check_last else 'first'} on this filesystem")

    # Scope first: the phase ran at all. The asserts after it say what the phase did with the check file. Both orders run,
    # because a phase that takes only the last file's exit code hides a red check listed before a passing file.
    def test_a_red_check_script_fails_the_mod_phase_in_either_order(self):
        for check_last in (True, False):
            with self.subTest(check_last=check_last):
                r = self.run_phase(self.tree_listing_check(f"red-check-{check_last}", check_last))
                self.assertIn("mod tests:", r.stdout, "the mod phase printed no count line, so it did not run")
                # Named failure: check.mjs never runs, because the phase globs *.test.mjs only.
                self.assertIn(self.SENTINEL, r.stdout + r.stderr, "mods/plain-diff/check.mjs did not run: the mod phase skips it")
                self.assertNotEqual(r.returncode, 0, "mods/plain-diff/check.mjs failed, and the mod phase still exited 0")

    # Green control: a passing check file leaves the phase green, so the fix cannot turn it red.
    def test_a_green_check_script_leaves_the_mod_phase_green(self):
        r = self.run_phase(self.make_tree("green-check", check=self.node_script(0, self.SENTINEL)))
        self.assertIn("mod tests:", r.stdout, "the mod phase printed no count line, so it did not run")
        self.assertEqual(r.returncode, 0, f"a passing mods/plain-diff/check.mjs turned the mod phase red:\n{r.stdout}{r.stderr}")

    # Green control: a red *.test.mjs already fails the phase.
    def test_a_red_test_file_fails_the_mod_phase(self):
        r = self.run_phase(self.make_tree("red-test", test=self.node_script(1)))
        self.assertIn("mod tests:", r.stdout, "the mod phase printed no count line, so it did not run")
        self.assertNotEqual(r.returncode, 0, "a red *.test.mjs passed the mod phase")


# The four pull-request lint steps of the `checks` job. Each runs on a pull request only when ci-scope.sh sets its flag, so a
# lint runs only when a file it reads changed. The flags stay out of ALL, as DERIVED_FLAGS does, so the exact-set cases
# above stay about the base flags.
LINT_FLAGS = ("lint_red_run", "lint_plan_refuter", "lint_ruling_kind", "lint_comment_narration")
LINT_STEPS = {  # flag -> the `name:` of the step it controls in checks.yml
    "lint_red_run": "Red-run trailer",
    "lint_plan_refuter": "Plan refuter line",
    "lint_ruling_kind": "Ruling kind check",
    "lint_comment_narration": "Comment narration check",
}


@unittest.skipUnless(BASH, "bash not on PATH")
class LintStepScope(unittest.TestCase):
    """Each lint flag is set by the paths its lint reads. A docs-only change sets none of the four. Fail-safe: a push, a
    schedule, a dispatch, an unreadable or empty diff, an unmapped path, and a change to the scope script or the workflow
    set all four on."""

    def lint_on(self, got, why):
        """-> the set of lint flags that are true. A flag that ci-scope.sh writes no line for fails here, by name."""
        for n in LINT_FLAGS:
            self.assertIn(n, got, f"{why}: ci-scope.sh writes no {n} line: {got}")
        return {n for n in LINT_FLAGS if got[n] == "true"}

    def test_docs_only_change_sets_all_four_lint_flags_off(self):
        for p in ("docs/notes.md", "README.md"):
            with self.subTest(path=p):
                self.assertEqual(self.lint_on(run([p]), p), set())

    def test_decision_record_sets_only_the_ruling_kind_lint(self):
        self.assertEqual(self.lint_on(run(["docs/decisions/x.md"]), "docs/decisions/x.md"), {"lint_ruling_kind"})

    def test_plan_record_sets_only_the_plan_refuter_lint(self):
        for p in ("docs/plans/x.md", "docs/plans/sub/x.md"):
            with self.subTest(path=p):
                self.assertEqual(self.lint_on(run([p]), p), {"lint_plan_refuter"})

    def test_each_lint_script_sets_its_own_flag(self):
        # A non-.md path sets lint_red_run and lint_comment_narration, since the red-run check and the narration check read
        # every non-.md file. Each script also sets the flag of its own lint.
        rows = (
            ("lint/check_red_run.py", {"lint_red_run", "lint_comment_narration"}),
            ("lint/check_plan_refuter.py", {"lint_red_run", "lint_comment_narration", "lint_plan_refuter"}),
            ("lint/check_ruling_kind.py", {"lint_red_run", "lint_comment_narration", "lint_ruling_kind"}),
            ("lint/check_comment_narration.py", {"lint_red_run", "lint_comment_narration"}),
        )
        for path, want in rows:
            with self.subTest(path=path):
                self.assertEqual(self.lint_on(run([path]), path), want)

    def test_hooks_change_sets_comment_narration_and_red_run_only(self):
        self.assertEqual(self.lint_on(run(["hooks/foo.py"]), "hooks/foo.py"), {"lint_red_run", "lint_comment_narration"})

    def test_lint_input_paths_set_the_flags_of_the_lints_that_read_them(self):
        rows = (
            ("CLAUDE.md", {"lint_ruling_kind"}),
            ("output-styles/shiv-stylisms.md", {"lint_ruling_kind"}),
            ("hooks/guard_core.py", {"lint_red_run", "lint_comment_narration", "lint_plan_refuter"}),
            ("lint/test_check_red_run.py", {"lint_red_run", "lint_comment_narration"}),
            ("lint/comment_scan.mjs", {"lint_red_run", "lint_comment_narration"}),
            ("lint/code_check_standard.json", {"lint_red_run", "lint_comment_narration"}),
            ("lint/layout.py", {"lint_red_run", "lint_comment_narration", "lint_plan_refuter", "lint_ruling_kind"}),
            ("lint/layout.json", {"lint_red_run", "lint_comment_narration", "lint_plan_refuter", "lint_ruling_kind"}),
        )
        for path, want in rows:
            with self.subTest(path=path):
                self.assertEqual(self.lint_on(run([path]), path), want)

    def test_md_under_a_test_folder_sets_red_run_only(self):
        for p in ("tests/notes.md", "test/notes.md", "__tests__/notes.md", "Tests/notes.md", "skills/x/tests/fixture.md"):
            with self.subTest(path=p):
                self.assertEqual(self.lint_on(run([p]), p), {"lint_red_run"})
        # Control: a file whose name starts with `tests` sits in no test folder, so it is docs.
        self.assertEqual(self.lint_on(run(["docs/tests-notes.md"]), "docs/tests-notes.md"), set())

    def test_full_size_docs_diff_sets_the_union_of_its_paths(self):
        paths = [f"docs/notes/{i}.md" for i in range(60)] + ["docs/decisions/x.md", "docs/plans/y.md", "tests/z.md"]
        self.assertEqual(self.lint_on(run(paths), "a 63-file docs diff"),
                         {"lint_red_run", "lint_plan_refuter", "lint_ruling_kind"})

    def test_unreadable_diff_sets_all_four_on(self):
        for base in ("0" * 40, ""):
            with self.subTest(base=base):
                self.assertEqual(self.lint_on(run(["docs/notes.md"], base=base), f"base {base!r}"), set(LINT_FLAGS))

    def test_empty_diff_sets_all_four_on(self):
        self.assertEqual(self.lint_on(run([]), "an empty diff"), set(LINT_FLAGS))

    def test_push_schedule_and_dispatch_set_all_four_on(self):
        for ev in ("push", "schedule", "workflow_dispatch"):
            with self.subTest(event=ev):
                self.assertEqual(self.lint_on(run(["docs/notes.md"], event=ev), ev), set(LINT_FLAGS))

    def test_unmapped_path_sets_all_four_on(self):
        self.assertEqual(self.lint_on(run(["zz-unmapped/blob.bin"]), "zz-unmapped/blob.bin"), set(LINT_FLAGS))

    def test_scope_script_or_workflow_change_sets_all_four_on(self):
        for p in (".github/scripts/ci-scope.sh", ".github/workflows/checks.yml"):
            with self.subTest(path=p):
                self.assertEqual(self.lint_on(run([p]), p), set(LINT_FLAGS))


def conjuncts(value):
    """The `&&` parts of one `${{ ... }}` expression, each stripped, as a set. None when the value is no such expression."""
    m = re.fullmatch(r"\$\{\{(.*)\}\}", value or "")
    return None if m is None else {part.strip() for part in m.group(1).split("&&")}


class LintStepWorkflow(unittest.TestCase):
    """checks.yml: each pull-request lint step names its scope flag with the pull-request condition, the scope job declares
    each flag, and the Silent undo check, which reads every merge, keeps the pull-request condition alone."""

    def setUp(self):
        path, why = job_workflow(os.path.join(HERE, ".."), "checks")
        if why:
            self.fail(why)
        with open(path, encoding="utf-8") as f:
            self.text = f.read()
        self.checks = job_block(self.text, "checks")
        self.scope = job_block(self.text, "scope")

    def step_if(self, name):
        """The `if:` of the `checks` job's step named `name`. A missing step, or a step with no if:, fails by name."""
        self.assertIsNotNone(self.checks, "checks.yml has no checks job")
        for s in step_blocks(self.checks):
            if step_key(s, "name") == name:
                raw = step_key(s, "if")
                self.assertIsNotNone(raw, f"the step {name!r} has no if:")
                return raw
        self.fail(f"the checks job has no step named {name!r}")

    def test_each_lint_step_names_its_flag_and_the_pull_request_condition(self):
        for flag, name in LINT_STEPS.items():
            with self.subTest(step=name):
                raw = self.step_if(name)
                self.assertEqual(conjuncts(raw), {f"needs.scope.outputs.{flag} == 'true'", "github.event_name == 'pull_request'"},
                                 f"{name} must run on {flag} and on a pull request; its if: is {raw!r}")

    def test_the_scope_job_declares_each_lint_flag(self):
        self.assertIsNotNone(self.scope, "checks.yml has no scope job")
        declared = dict(re.findall(r"^      (\w+): \$\{\{ steps\.scope\.outputs\.(\w+) \}\}[ \t]*$", self.scope, re.M))
        for flag in LINT_FLAGS:
            with self.subTest(flag=flag):
                self.assertEqual(declared.get(flag), flag, f"the scope job does not declare {flag} from steps.scope.outputs")

    def test_the_silent_undo_check_stays_on_the_pull_request_condition_only(self):
        raw = self.step_if("Silent undo check")
        self.assertEqual(conjuncts(raw), {"github.event_name == 'pull_request'"}, f"the Silent undo check's if: is {raw!r}")


@unittest.skipUnless(BASH, "bash not on PATH")
class MutationReport(unittest.TestCase):
    """The mutation_report output: on a pull request only from a `batch-` branch, and on every other event."""

    # Named failure: the mutation-report job starts on every pull request, or on none, not only the batch ones.
    def test_only_a_batch_pull_request_turns_it_on_and_a_push_always_does(self):
        feature = run(["README.md"], head_ref="feature-x")
        self.assertIn("mutation_report", feature, feature)
        self.assertEqual(feature["mutation_report"], "false", f"a pull request from feature-x: {feature}")
        batch = run(["README.md"], head_ref="batch-11")
        self.assertEqual(batch["mutation_report"], "true", f"a pull request from batch-11: {batch}")
        push = run(["README.md"], event="push")
        self.assertEqual(push["mutation_report"], "true", f"a push: {push}")


if __name__ == "__main__":
    unittest.main()
