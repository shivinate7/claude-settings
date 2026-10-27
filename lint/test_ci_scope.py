#!/usr/bin/env python3
"""CLI tests for the scope detector (.github/scripts/ci-scope.sh).

Each case builds a scratch git repo, commits a base, commits the changed paths, runs the script
with EVENT and BASE_SHA set, and reads the name=value lines it wrote to $GITHUB_OUTPUT.
CI_SCOPE overrides the script path (for a successor). Needs bash on PATH.

Output names pinned (the `scope` job re-exports them as job outputs):
  JOB_FLAGS  one per check job except the lint job `checks`: checks_windows, checks_windows_merge,
             checks_windows_rest, checks_macos, shell_macos, pointer_windows
  STEP_FLAGS code, guard, sweep, mods, shoot (the suite flags; shoot selects the whole checks-shoot job)

Run with:  python3 lint/test_ci_scope.py -v
"""
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.environ.get("CI_SCOPE") or os.path.join(HERE, "..", ".github", "scripts", "ci-scope.sh")
JOB_FLAGS = ["checks_windows", "checks_windows_merge", "checks_windows_rest", "checks_macos", "shell_macos", "pointer_windows"]
STEP_FLAGS = ["code", "guard", "sweep", "mods", "shoot"]
ALL = JOB_FLAGS + STEP_FLAGS
BASH = shutil.which("bash")


def git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def run(paths, event="pull_request", base="auto", existing=(), landed=None):
    """-> {name: 'true'|'false'} the script wrote. `paths` are committed on top of one base commit."""
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
        for p in existing:  # in the base commit, so the head commit modifies them
            os.makedirs(os.path.dirname(os.path.join(d, p)), exist_ok=True)
            open(os.path.join(d, p), "w").write("old\n")
        git(d, "add", "-A")
        git(d, "commit", "-qm", "base")
        sha = git(d, "rev-parse", "HEAD")
        for p in paths:
            full = os.path.join(d, p)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            open(full, "w").write("changed\n")
        git(d, "add", "-A")
        git(d, "commit", "-qm", "head", "--allow-empty")
        out = os.path.join(d, "..", f"out-{os.getpid()}.txt")
        env = dict(os.environ, EVENT=event, GITHUB_OUTPUT=out,
                   BASE_SHA=sha if base == "auto" else base)
        r = subprocess.run([BASH, os.path.abspath(SCRIPT)], cwd=d, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
        lines = open(out).read().split()
        os.remove(out)
        return dict(l.split("=", 1) for l in lines)


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

    # Mod and map-skill tests run as a step of the checks, checks-windows and checks-macos jobs, selected by the
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
    MOD_ARMS = ["mods/zz-new/a.mjs", "lint/test_scanner_traps.mjs", "skills/plain-english-map/README.md"]

    def test_each_mods_arm_starts_the_windows_and_macos_jobs(self):
        for p in self.MOD_ARMS:
            with self.subTest(path=p, edit=True):
                want = {"mods", "checks_windows", "checks_macos"} | ({"code"} if p.startswith("lint/") else set())
                self.assertEqual(self.true_set(run([p], existing=[p])), want)
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

    # bin/sim-test and its suite run in the shell-macos job only, like bin/ios-ship.
    def test_sim_test_edit_turns_on_only_the_macos_shell_job(self):
        for p in ("bin/sim-test", "lint/test_sim_test.sh"):
            with self.subTest(path=p):
                self.assertEqual(self.true_set(run([p], existing=[p])), {"shell_macos", "code"})

    # bin/shoot's suite installs a browser, so only its own paths turn `shoot` on. An edit sets `code` and `shoot`
    # and no other flag; an unrelated code change leaves `shoot` off.
    def test_shoot_edit_turns_on_only_the_shoot_suite(self):
        for p in ("bin/shoot", "lint/test_shoot.mjs", "testing/skip-locally-fail-in-ci.mjs", ".github/shoot/package-lock.json",
                  "actions/playwright-setup/action.yml"):
            with self.subTest(path=p):
                self.assertEqual(self.true_set(run([p], existing=[p])), {"code", "shoot"})
        self.assertFlags(run(["lint/test_verdict.py"], existing=["lint/test_verdict.py"]), want_false=["shoot"])

if __name__ == "__main__":
    unittest.main()
