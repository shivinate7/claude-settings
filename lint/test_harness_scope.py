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


def run(paths, event="pull_request", base="auto", before="auto", existing=()):
    """-> {name: 'true'|'false'} the script wrote. `paths` are committed on top of one base commit."""
    with tempfile.TemporaryDirectory() as d:
        git(d, "init", "-q")
        git(d, "config", "user.email", "t@t")
        git(d, "config", "user.name", "t")
        git(d, "config", "commit.gpgsign", "false")
        open(os.path.join(d, "seed.txt"), "w").write("seed\n")
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


if __name__ == "__main__":
    unittest.main()
