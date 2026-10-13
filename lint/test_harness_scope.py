#!/usr/bin/env python3
"""CLI tests for the scope detector (.github/scripts/harness-scope.sh).

Each case builds a scratch git repo, commits a base, commits the changed paths, runs the script
with EVENT, BASE_SHA and BEFORE_SHA set, and reads the name=value lines it wrote to $GITHUB_OUTPUT.
HARNESS_SCOPE overrides the script path (for a successor). Needs bash on PATH.

Output names pinned (the `scope` job re-exports them as job outputs):
  JOB_FLAGS  one per gate job except the lint job `gates`: gates_windows, gates_windows_merge,
             gates_windows_rest, gates_macos, shell_macos, pointer_windows
  STEP_FLAGS code, guard, sweep (the suite flags the steps inside a job read)

Run with:  python3 lint/test_harness_scope.py -v
"""
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.environ.get("HARNESS_SCOPE") or os.path.join(HERE, "..", ".github", "scripts", "harness-scope.sh")
JOB_FLAGS = ["gates_windows", "gates_windows_merge", "gates_windows_rest", "gates_macos", "shell_macos", "pointer_windows"]
STEP_FLAGS = ["code", "guard", "sweep"]
ALL = JOB_FLAGS + STEP_FLAGS
BASH = shutil.which("bash")


def git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def run(paths, event="pull_request", base="auto", before="auto", existing=(), landed=None):
    """-> {name: 'true'|'false'} the script wrote. `paths` are committed on top of one base commit."""
    with tempfile.TemporaryDirectory() as d:
        git(d, "init", "-q")
        git(d, "config", "user.email", "t@t")
        git(d, "config", "user.name", "t")
        git(d, "config", "commit.gpgsign", "false")
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
                   BASE_SHA=sha if base == "auto" else base, BEFORE_SHA=sha if before == "auto" else before)
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
        self.assertFlags(got, want_true=["gates_windows_merge", "code"])

    def test_guard_change_turns_the_guard_suites_on(self):
        got = run(["hooks/guard.py"])
        self.assertFlags(got, want_true=["gates_windows", "gates_macos", "guard", "sweep", "code"])

    def test_a_merge_change_leaves_a_job_that_never_runs_merge_suites_off(self):
        got = run(["merge/merge.py"])
        self.assertFlags(got, want_false=["pointer_windows", "shell_macos"])

    def test_workflow_or_scope_script_change_runs_everything(self):
        for p in (".github/workflows/gates.yml", ".github/scripts/harness-scope.sh"):
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

    def test_push_with_an_unreadable_range_runs_everything(self):
        self.assertFlags(run(["README.md"], event="push", before="e" * 40), want_true=ALL)

    # Map gaps found in review: each path is read by a suite in another job.
    def test_merge_tool_change_turns_on_the_suites_that_load_it(self):
        self.assertFlags(run(["merge/merge.py"]), want_true=["gates_windows", "gates_macos", "guard", "gates_windows_merge"])

    def test_record_slug_checker_change_turns_on_the_guard_suites(self):
        self.assertFlags(run(["lint/check_record_slugs.py"]), want_true=["gates_windows", "gates_macos", "guard", "code"])

    def test_janitor_launcher_change_turns_on_the_install_suite(self):
        self.assertFlags(run(["bin/claude-janitor"]), want_true=["gates_windows", "shell_macos"])

    def test_silent_undo_checker_change_turns_on_the_merge_job(self):
        self.assertFlags(run(["lint/check_silent_undo.py"]), want_true=["gates_windows_merge"])

    def test_session_start_change_turns_on_the_unknown_read_contract_job(self):
        self.assertFlags(run(["hooks/session_start.sh"]), want_true=["gates_windows_rest"])

    def test_a_new_file_in_a_landed_dir_turns_on_the_install_suite(self):
        for p in ("agents/new.md", "skills/new/SKILL.md", "output-styles/new.md", "lint/new.py"):
            self.assertFlags(run([p]), want_true=["gates_windows", "shell_macos"])

    def test_a_modified_md_under_skills_turns_on_nothing(self):
        self.assertFlags(run(["skills/old/SKILL.md"], existing=["skills/old/SKILL.md"]), want_false=ALL)

    def test_a_new_file_in_hooks_or_janitor_turns_on_the_install_suite(self):
        for p in ("hooks/new.py", "janitor/new.py"):
            self.assertFlags(run([p]), want_true=["gates_windows", "shell_macos"])

    def test_the_landed_dirs_come_from_landed_dirs_txt(self):
        # A made-up dir in the scratch repo's landed-dirs.txt: the script reads the file, it does not copy the list.
        self.assertFlags(run(["zz-made-up/new.md"], landed=["zz-made-up"]), want_true=["gates_windows", "shell_macos"])

    def test_an_empty_or_comment_only_landed_list_turns_everything_on(self):
        for landed in ([], ["# only a comment", ""]):
            self.assertFlags(run(["docs/new.md"], landed=landed), want_true=ALL)

    def test_a_trailing_slash_in_landed_dirs_is_read_as_the_dir(self):
        self.assertFlags(run(["zz-made-up/new.md"], landed=["zz-made-up/"]), want_true=["gates_windows", "shell_macos"])

    # Cut F: gates-windows-guard and gates-mutate-guard skip on the `guard` flag. The slice selector
    # (GUARD_TESTS) is read from hooks/test_guard.py, so an edit to that file must turn `guard` on,
    # or a pull request that changes the slice would run no guard job at all.
    def test_the_guard_selector_and_its_harness_turn_the_guard_flag_on(self):
        for p in ("hooks/test_guard.py", "hooks/mutate_guard.py", "hooks/guard.py"):
            self.assertFlags(run([p]), want_true=["guard"])

    # Review finding on #305: the guard suite reads these two paths, but the rules did not set `guard`,
    # so after cut F a pull request touching them ran the guard suite in no job (false green).
    def test_a_new_file_under_a_landed_dir_turns_on_the_guard_suite(self):
        self.assertFlags(run(["lint/zz_new.py"]), want_true=["guard"])

    def test_the_janitor_launcher_turns_on_the_guard_suite(self):
        self.assertFlags(run(["bin/claude-janitor"]), want_true=["guard"])

    # Control: a docs-only path must keep `guard` off, or the new rules over-trigger (false red).
    def test_a_docs_only_path_keeps_the_guard_flag_off(self):
        for p in ("README.md", "decisions/some-record.md"):
            self.assertFlags(run([p]), want_false=["guard"])

    # Round 2 hole: lint/guard_log_report.py imports hooks/guard_core.py at load, and decision_watch
    # reads guard.log through it at run time. So a change to it must select the same jobs as
    # lint/_transcript.py, the other module the decision watch loads (the rules at its line 36, 51).
    def test_guard_log_reader_change_selects_the_jobs_of_the_transcript_reader(self):
        reader = self.true_set(run(["lint/guard_log_report.py"]))
        self.assertEqual(reader, self.true_set(run(["lint/_transcript.py"])))
        self.assertTrue({"gates_windows_rest", "gates_macos", "code", "guard"} <= reader, reader)

    # Guard family: hooks/guard_<anything>.py is split out of hooks/guard.py. Each sibling must set
    # exactly the flags guard.py sets, as a new file and as an edit. Today the generic hooks/* rule
    # gives a new sibling no sweep flag, and an edited one no Windows or shell job.
    GUARD_SIBLINGS = ["hooks/guard_core.py", "hooks/guard_merge.py", "hooks/guard_rules.py"]

    def true_set(self, got):
        return {n for n in ALL if got[n] == "true"}

    def test_guard_sibling_new_file_sets_the_same_flags_as_guard_py(self):
        want = run(["hooks/guard.py"])
        self.assertFlags(want, want_true=["gates_windows", "gates_windows_rest", "gates_macos", "code", "guard", "sweep"],
                         want_false=["gates_windows_merge", "pointer_windows"])
        for p in self.GUARD_SIBLINGS:
            with self.subTest(path=p):
                self.assertEqual(run([p]), want)

    def test_guard_sibling_edit_sets_the_same_flags_as_guard_py(self):
        want = run(["hooks/guard.py"], existing=["hooks/guard.py"])
        self.assertFlags(want, want_true=["gates_windows", "gates_windows_rest", "gates_macos", "code", "guard", "sweep"],
                         want_false=["gates_windows_merge", "shell_macos", "pointer_windows"])
        for p in self.GUARD_SIBLINGS:
            with self.subTest(path=p):
                self.assertEqual(run([p], existing=[p]), want)

    # Control: the guard test file keeps today's flags. A family rule must not catch it.
    def test_guard_test_file_keeps_its_current_flags(self):
        p = "hooks/guard_test_x.py"
        self.assertEqual(self.true_set(run([p])),
                         {"gates_windows", "gates_windows_rest", "gates_macos", "shell_macos", "code", "guard"})
        self.assertEqual(self.true_set(run([p], existing=[p])), {"gates_windows_rest", "gates_macos", "code", "guard"})

    # Control: the guard selector test keeps today's flags.
    def test_test_guard_keeps_its_current_flags(self):
        p = "hooks/test_guard.py"
        self.assertEqual(self.true_set(run([p])), {"gates_windows", "gates_macos", "shell_macos", "code", "guard"})
        self.assertEqual(self.true_set(run([p], existing=[p])), {"gates_windows", "gates_macos", "code", "guard"})

    # Mod tests run as a step of the `gates` job (Linux), gated on the `mods` flag. The flag is its
    # own: today a mods/ path falls to the unmapped rule, which turns every flag on. ALL stays as it
    # is, so the cases below carry the mods check, and a missing flag reads as a FAIL here.
    def test_a_mods_path_sets_the_mods_flag(self):
        for p in ("mods/plain-diff/check.mjs", "mods/session-board/session-board.test.mjs"):
            with self.subTest(path=p):
                self.assertEqual(run([p]).get("mods"), "true")
        self.assertEqual(run(["README.md", "mods/plain-diff/check.mjs"]).get("mods"), "true")

    def test_a_mods_only_diff_sets_no_other_flag(self):
        got = run(["mods/plain-diff/check.mjs"])
        self.assertEqual(got.get("mods"), "true", got)
        self.assertFlags(got, want_false=ALL)

    def test_a_docs_only_diff_leaves_the_mods_flag_off(self):
        self.assertEqual(run(["README.md", "decisions/some-record.md"]).get("mods"), "false")

    def test_the_fail_safe_cases_set_the_mods_flag(self):
        cases = {
            "scope script": run([".github/scripts/harness-scope.sh"]),
            "workflow": run([".github/workflows/gates.yml"]),
            "unmapped path": run(["zz-unmapped/blob.bin"]),
            "unreadable diff": run(["README.md"], base="f" * 40),
            "empty base": run(["README.md"], base=""),
            "push": run(["README.md"], event="push"),
            "schedule": run(["README.md"], event="schedule"),
            "dispatch": run(["README.md"], event="workflow_dispatch"),
        }
        for name, got in cases.items():
            with self.subTest(case=name):
                self.assertEqual(got.get("mods"), "true", got)


if __name__ == "__main__":
    unittest.main()
