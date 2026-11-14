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

Run with:  python3 lint/test_ci_scope.py -v
"""
import ast
import os
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
SCRIPT = os.environ.get("CI_SCOPE") or os.path.join(HERE, "..", ".github", "scripts", "ci-scope.sh")
JOB_FLAGS = ["checks_windows", "checks_windows_merge", "checks_windows_rest", "checks_macos", "shell_macos", "pointer_windows"]
STEP_FLAGS = ["code", "guard", "sweep", "mods", "shoot"]
# Flags derived from others, kept out of JOB_FLAGS so the exact-set cases below stay about the base flags:
# checks_windows_sweep is set with checks_windows_rest. checks_guard is set when both `code` and `guard` are set, or
# directly by the arm for actions/playwright-setup and .github/shoot (the paths checks-guard installs from).
DERIVED_FLAGS = ["checks_windows_sweep", "checks_guard"]
ALL = JOB_FLAGS + STEP_FLAGS
BASH = shutil.which("bash")


def git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def run(paths, event="pull_request", base="auto", existing=(), landed=None, head_ref="", moves=None):
    """-> {name: 'true'|'false'} the script wrote. `paths` are committed on top of one base commit. `head_ref` is HEAD_REF,
    empty when not given, so no HEAD_REF of the caller's environment reaches the script. `moves` maps an old path to its new
    one, or to None for a delete: the old path is in the base, and a move keeps the content, so git sees a rename."""
    moves = moves or {}
    with tempfile.TemporaryDirectory() as d:
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
        for p in list(existing) + list(moves):  # in the base commit, so the head commit modifies, moves or deletes them
            os.makedirs(os.path.dirname(os.path.join(d, p)), exist_ok=True)
            open(os.path.join(d, p), "w").write("old\n")
        git(d, "add", "-A")
        git(d, "commit", "-qm", "base")
        sha = git(d, "rev-parse", "HEAD")
        for old, new in moves.items():
            os.remove(os.path.join(d, old))
            if new is not None:
                os.makedirs(os.path.dirname(os.path.join(d, new)), exist_ok=True)
                open(os.path.join(d, new), "w").write("old\n")
        for p in paths:
            full = os.path.join(d, p)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            open(full, "w").write("changed\n")
        git(d, "add", "-A")
        git(d, "commit", "-qm", "head", "--allow-empty")
        out = os.path.join(d, "..", f"out-{os.getpid()}.txt")
        env = dict(os.environ, EVENT=event, GITHUB_OUTPUT=out, HEAD_REF=head_ref,
                   BASE_SHA=sha if base == "auto" else base)
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

    # A non-.md path under mods/ also sets `code`. The whole-tree readers (retired names and repo, glossary, hook catalog) run only when
    # `code` or a doc flag is on, so a mods-only pull request must start them. A .md path under mods/ keeps `code` off.
    def test_a_mods_only_diff_sets_the_mod_jobs_code_and_no_other_flag(self):
        got = run(["mods/plain-diff/check.mjs"])
        self.assertFlags(got, want_true=["mods", "code"] + self.MOD_JOBS,
                         want_false=[n for n in ALL if n not in ["mods", "code"] + self.MOD_JOBS])

    def test_a_non_md_mods_path_sets_code(self):
        for p in ("mods/x/y/z.mjs", "mods/x/data.json", "mods/x/y/check.test.mjs"):
            with self.subTest(path=p):
                self.assertEqual(run([p])["code"], "true", f"{p} does not set code, so the whole-tree readers skip it")

    def test_a_md_path_under_mods_keeps_code_off(self):
        for p in ("mods/x/README.md", "mods/x/y/notes.md"):
            with self.subTest(path=p):
                self.assertEqual(run([p])["code"], "false", f"{p} sets code")

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
    # pull request must run the CI step. It keeps `code`, which its lint suites read. A non-.md mods/ path keeps `code` too.
    MOD_ARMS = ["mods/zz-new/a.mjs", "lint/test_scanner_traps.mjs", "skills/plain-english-map/README.md", ".gitignore"]

    def test_each_mods_arm_starts_the_windows_and_macos_jobs(self):
        for p in self.MOD_ARMS:
            with self.subTest(path=p, edit=True):
                code_arm = p.startswith("lint/") or (p.startswith("mods/") and not p.endswith(".md")) or p == ".gitignore"
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
    # Every reference/*.md is read by the page suite (skills/waiting-page/tests/page.test.mjs), whose job gates on `shoot` too.
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

    # actions/playwright-setup has four callers (checks.yml): checks-guard and checks-guard-2 gate on checks_guard
    # alone, and checks-shoot and checks-waiting-page gate on shoot alone. An edit to the action must set
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


# The doc groups (lane ci-skip-untouched-steps, slice 3). ci-scope.sh sets one doc_<group> flag per group, and a
# docs-only step's scope condition reads the flags of the groups it reads (lint/test_checks_step_scope.py).
DOC_GROUPS = ("decisions", "rules", "skills", "agents", "glossary", "map", "other", "any")
DOC_FLAGS = ["doc_" + g for g in DOC_GROUPS]
# Each docs-only path with the groups it sets. Explicit, so the script is checked against this table, not against doc_groups.
DOC_CASES = [
    ("docs/decisions/x.md", {"decisions", "any"}),
    ("docs/decisions/sub/x.md", {"decisions", "any"}),  # a nested path: bash's `*` matches `/`, so the arm still holds
    ("skills/foo/SKILL.md", {"skills", "any"}),
    ("skills/a/b/c.md", {"skills", "any"}),
    ("agents/x.md", {"agents", "any"}),
    ("agents/x/y.md", {"any"}),  # the empty agents/*/*.md arm: deleted, it falls to agents/*.md and sets doc_agents
    ("CLAUDE.md", {"rules", "any"}),
    (".claude/CLAUDE.md", {"rules", "any"}),
    (".claude/rules/x.md", {"any"}),  # no group arm names it: `any` only
    ("AGENTS.md", {"any"}),  # no group arm names it: `any` only
    ("output-styles/shiv-stylisms.md", {"rules", "any"}),
    ("GLOSSARY.md", {"glossary", "any"}),
    ("README.md", {"glossary", "any"}),
    ("docs/map/x.md", {"map", "any"}),
    ("docs/debts/x.md", {"other", "any"}),
    ("docs/notes.md", {"other", "any"}),
    ("mods/x/README.md", {"other", "any"}),
    ("mods/x/y/README.md", {"any"}),  # the empty mods/*/*/*.md arm: deleted, it falls to mods/*/README.md and sets doc_other
    ("unlisted/x.md", {"any"}),
]


def doc_groups(path):
    """The doc groups a path sets, by the rules of ci-scope.sh: every .md is in `any`, and a path in no other group sets `any` only.
    Read by lint/test_checks_step_scope.py to check the names a step's entry reads against the flags its `if:` reads."""
    if not path.endswith(".md"):
        return set()
    g = {"any"}
    if path.startswith("docs/decisions/"):
        g.add("decisions")
    elif path in ("CLAUDE.md", ".claude/CLAUDE.md") or path.startswith("output-styles/"):
        g.add("rules")
    elif path.startswith("skills/"):
        g.add("skills")
    elif path.startswith("agents/") and "/" not in path[len("agents/"):]:
        g.add("agents")
    elif path in ("GLOSSARY.md", "README.md"):
        g.add("glossary")
    elif path.startswith("docs/map/"):
        g.add("map")
    elif path.startswith("docs/") or (path.startswith("mods/") and path.count("/") == 2 and path.endswith("/README.md")):
        g.add("other")
    return g


@unittest.skipUnless(BASH, "bash not on PATH")
class DocGroups(unittest.TestCase):
    """The doc_* flags: each exists, is true for its paths and false for the others, and leaves `code` and every job flag alone.
    Each case is an edit to a tracked file (existing), so a new file under a landed dir (agents/, skills/) sets code by its own rule."""

    def assertDocFlags(self, got, want, path):
        for f in DOC_FLAGS:
            self.assertIn(f, got, f"output {f} missing for {path}: {got}")
        for g in DOC_GROUPS:
            self.assertEqual(got["doc_" + g], "true" if g in want else "false", f"doc_{g} for {path}: {got}")

    def assertJobFlagsOff(self, got, path):
        for n in ALL:
            self.assertIn(n, got, f"output {n} missing for {path}: {got}")
            self.assertEqual(got[n], "false", f"{n} set by {path}: {got}")

    def test_each_doc_flag_is_true_for_its_paths_and_false_for_the_rest(self):
        for path, want in DOC_CASES:
            with self.subTest(path=path):
                self.assertDocFlags(run([path], existing=[path]), want, path)

    def test_a_decision_doc_sets_doc_decisions_and_doc_any_only(self):
        got = run(["docs/decisions/x.md"], existing=["docs/decisions/x.md"])
        self.assertDocFlags(got, {"decisions", "any"}, "docs/decisions/x.md")

    def test_a_docs_notes_change_sets_doc_other_and_doc_any_only(self):
        got = run(["docs/notes.md"], existing=["docs/notes.md"])
        self.assertDocFlags(got, {"other", "any"}, "docs/notes.md")

    # A move keeps the content, so git reads it as a rename. --no-renames lists the old path, which sets doc_decisions; the new
    # path sets only doc_any. Named failure: a diff that shows only the new name of a move sets no doc_decisions.
    def test_a_move_out_of_docs_decisions_sets_doc_decisions_through_the_old_path(self):
        path = "docs/decisions/x.md"
        got = run([], moves={path: "unlisted/moved.md"})  # no `paths`: run() would rewrite the moved file's content
        self.assertDocFlags(got, {"decisions", "any"}, f"{path} moved to unlisted/moved.md")
        self.assertJobFlagsOff(got, f"{path} moved to unlisted/moved.md")

    # Named failure: a diff that drops deleted files (--diff-filter) sets no doc flag for a decision doc that is removed.
    def test_a_delete_of_a_decision_doc_sets_doc_decisions(self):
        path = "docs/decisions/x.md"
        got = run([], moves={path: None})
        self.assertDocFlags(got, {"decisions", "any"}, f"deleted {path}")
        self.assertJobFlagsOff(got, f"deleted {path}")

    # Control, the fail-safe: the doc arms match a lower-case .md only. An upper-case .MD name falls to the catch-all arm, so every
    # flag is on. That is a false alarm, never a skipped step. It is not a DOC_CASES row: that loop expects a docs-only change.
    def test_an_upper_case_md_name_takes_the_fail_safe_arm(self):
        path = "docs/decisions/x.MD"
        got = run([path], existing=[path])
        self.assertDocFlags(got, set(DOC_GROUPS), path)
        for n in ALL:
            self.assertEqual(got.get(n), "true", f"{n} is off for {path}, so the catch-all arm no longer covers it: {got}")

    def test_a_new_decision_doc_sets_its_flags_and_no_job_flag(self):
        # docs/decisions is in no landed dir, so a new file there sets nothing but its doc flags.
        got = run(["docs/decisions/new.md"])
        self.assertDocFlags(got, {"decisions", "any"}, "docs/decisions/new.md")
        self.assertJobFlagsOff(got, "docs/decisions/new.md")

    def test_every_doc_flag_is_true_on_push_schedule_and_dispatch(self):
        for ev in ("push", "schedule", "workflow_dispatch"):
            with self.subTest(event=ev):
                got = run(["docs/decisions/x.md"], event=ev)
                for f in DOC_FLAGS:
                    self.assertEqual(got.get(f), "true", f"{f} on {ev}: {got}")

    def test_every_doc_flag_is_true_on_an_unreadable_diff(self):
        for base in ("0" * 40, ""):
            with self.subTest(base=base):
                got = run(["docs/decisions/x.md"], base=base)
                for f in DOC_FLAGS:
                    self.assertEqual(got.get(f), "true", f"{f} on an unreadable diff: {got}")

    def test_every_doc_flag_is_true_when_the_scope_script_or_the_workflow_changes(self):
        for p in (".github/scripts/ci-scope.sh", ".github/workflows/checks.yml"):
            with self.subTest(path=p):
                got = run([p])
                for f in DOC_FLAGS:
                    self.assertEqual(got.get(f), "true", f"{f} for {p}: {got}")

    def test_a_docs_only_change_leaves_code_false_whatever_its_doc_flags(self):
        for path, _ in DOC_CASES:
            with self.subTest(path=path):
                got = run([path], existing=[path])
                self.assertIn("code", got, got)
                self.assertEqual(got["code"], "false", f"{path} set code: {got}")
        # Control: a code change still sets code, so the check above can fail.
        self.assertEqual(run(["hooks/guard.py"])["code"], "true")

    def test_a_docs_only_change_turns_no_job_or_suite_flag_on(self):
        for path in ("docs/decisions/x.md", "docs/notes.md"):
            with self.subTest(path=path):
                self.assertJobFlagsOff(run([path], existing=[path]), path)


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
        cls.run_dir = _test_temp.run_folder()

    @classmethod
    def tearDownClass(cls):
        tracked_tree.rm_tree(cls.run_dir)

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
