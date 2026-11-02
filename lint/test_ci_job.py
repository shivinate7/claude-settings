#!/usr/bin/env python3
"""Fixture suite for bin/ci-job: each case writes a workflow into a throwaway repo and runs one job.

Red cases: a multi-line step whose last line fails, a missing tool (named, behind xargs, or exit 127),
a `uses:` step, an `if:` or env expression the runner cannot read, and a pull-request step with no base.
None of them may read PASS. The last class plans the real checks job: every step gets one line.
The last two classes: the code-check step from a copied install, and a step quiet past the stall limit.
Run: python3 lint/test_ci_job.py
"""
import functools
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: every temp path comes from this run's folder
RUN_FOLDER = _test_temp.run_folder()
CHECKOUT = os.path.abspath(os.path.join(HERE, ".."))
CI_JOB = os.path.join(HERE, "..", "bin", "ci-job")
CHECKS = os.path.join(HERE, "..", ".github", "workflows", "checks.yml")
STALL_WATCH = os.path.join(HERE, "..", "hooks", "stall_watch.py")
ENV = _test_git.apply(dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull, GIT_AUTHOR_NAME="t",
                           GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t"))
ENV.pop("VERDICT_LOG", None)


def workflow(*steps):
    return "name: t\non: push\njobs:\n  lane:\n    runs-on: ubuntu-latest\n    steps:\n" + "".join(steps) + \
        "\n  other:\n    runs-on: ubuntu-latest\n    steps:\n      - run: exit 1\n"


def step(name, run=None, **keys):
    text = "      - name: %s\n" % name
    for key, value in keys.items():
        key = key.replace("_", "-")
        if isinstance(value, dict):
            text += "        %s:\n" % key + "".join("          %s: %s\n" % kv for kv in value.items())
        else:
            text += "        %s: %s\n" % (key, value)
    if run is not None:
        if "\n" in run:
            text += "        run: |\n" + "".join("          %s\n" % line for line in run.split("\n"))
        else:
            text += "        run: %s\n" % run
    return text + "\n"


class Job(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="cijob_", dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, self.root, True)
        subprocess.run(["git", "init", "-q", "-b", "main", self.root], check=True, env=ENV)
        self.log = os.path.join(self.root, "verdict.log")

    def job_call(self, *steps, args=(), env=None, script=CI_JOB):
        """argv and env of one run of the job: its workflow is written into the throwaway repo."""
        path = os.path.join(self.root, "wf.yml")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(workflow(*steps))
        env = {**ENV, "VERDICT_LOG": self.log, **{k: v for k, v in os.environ.items() if k == "VERDICT_HEARTBEAT"},
               **(env or {})}
        return [sys.executable, script, "lane", "--workflow", path, *args], env

    def run_job(self, *steps, args=(), env=None, script=CI_JOB):
        argv, env = self.job_call(*steps, args=args, env=env, script=script)
        done = subprocess.run(argv, cwd=self.root, capture_output=True, text=True, env=env, timeout=120)
        lines = [ln for ln in done.stdout.splitlines() if not ln.startswith("log=")]
        return done.returncode, lines, done.stdout + done.stderr

    def verdicts(self, lines):
        return [ln.split()[0] if not ln.startswith("not run locally") else "not run locally" for ln in lines]


class Steps(Job):
    def test_a_passing_step_passes_and_the_job_exits_zero(self):
        rc, lines, out = self.run_job(step("ok", "true"))
        self.assertEqual((rc, self.verdicts(lines)), (0, ["PASS"]), out)

    def test_a_multi_line_step_runs_whole_and_its_last_line_fails_it(self):
        rc, lines, out = self.run_job(step("block", "true\necho first > first.txt\nexit 3"))
        self.assertEqual((rc, self.verdicts(lines)), (1, ["FAIL"]), out)
        self.assertTrue(os.path.exists(os.path.join(self.root, "first.txt")), out)

    def test_a_multi_line_step_that_passes_passes(self):
        rc, lines, out = self.run_job(step("block", "echo a > a.txt\necho b > b.txt"))
        self.assertEqual((rc, self.verdicts(lines)), (0, ["PASS"]), out)
        self.assertTrue(os.path.exists(os.path.join(self.root, "b.txt")), out)

    def test_the_verdict_line_is_not_a_heartbeat(self):
        os.environ["VERDICT_HEARTBEAT"] = "1"
        try:
            rc, lines, out = self.run_job(step("slow", "sleep 2.5"))
        finally:
            del os.environ["VERDICT_HEARTBEAT"]
        self.assertEqual((rc, self.verdicts(lines)), (0, ["PASS"]), out)
        self.assertNotIn("still running", lines[0])

    def test_one_line_per_step_in_order(self):
        rc, lines, out = self.run_job(step("one", "true"), step("two", "false"), step("three", "true"))
        self.assertEqual(self.verdicts(lines), ["PASS", "FAIL", "PASS"], out)
        self.assertEqual([ln.split(":")[0].split(None, 1)[1] for ln in lines], ["one", "two", "three"], out)
        self.assertEqual(rc, 1)

    def test_working_directory_is_kept(self):
        os.makedirs(os.path.join(self.root, "sub"))
        rc, lines, out = self.run_job(step("here", "test -f marker", working_directory="sub"),
                                      step("mark", "true"))
        self.assertEqual(self.verdicts(lines)[0], "FAIL", out)
        open(os.path.join(self.root, "sub", "marker"), "w").close()
        rc, lines, out = self.run_job(step("here", "test -f marker", working_directory="sub"))
        self.assertEqual((rc, self.verdicts(lines)), (0, ["PASS"]), out)

    def test_plan_runs_nothing(self):
        rc, lines, out = self.run_job(step("write", "echo x > planned.txt"), args=("--plan",))
        self.assertEqual(lines, ["would run       write"], out)
        self.assertFalse(os.path.exists(os.path.join(self.root, "planned.txt")))


class Skips(Job):
    """A step that skips tests reads SKIP, never PASS, and never hides a FAIL (debt verdict-skip-reads-pass)."""

    SKIPPED = step("unit", "printf 'Ran 1 test in 0.000s\\n\\nOK (skipped=1)\\n'")

    def test_a_step_that_skips_reads_skip_and_the_job_exits_zero(self):
        rc, lines, out = self.run_job(self.SKIPPED, step("ok", "true"))
        self.assertEqual((rc, self.verdicts(lines)), (0, ["SKIP", "PASS"]), out)
        self.assertRegex(lines[0], r": SKIP .*\b1 skipped\b", out)

    def test_a_skip_does_not_hide_a_fail(self):
        rc, lines, out = self.run_job(self.SKIPPED, step("bad", "false"))
        self.assertEqual((rc, self.verdicts(lines)), (1, ["SKIP", "FAIL"]), out)


class Unknowns(Job):
    def test_a_missing_tool_is_unknown_never_pass(self):
        rc, lines, out = self.run_job(step("tool", "no-such-tool-c69 --check ."))
        self.assertEqual((rc, self.verdicts(lines)), (2, ["unknown"]), out)
        self.assertIn("tool missing: no-such-tool-c69", lines[0])

    def test_a_missing_tool_behind_xargs_is_unknown(self):
        rc, lines, out = self.run_job(step("tool", "git ls-files -z | xargs -0 no-such-tool-c69 --strict"))
        self.assertEqual(self.verdicts(lines), ["unknown"], out)
        self.assertIn("no-such-tool-c69", lines[0])

    def test_a_missing_tool_in_a_later_line_is_unknown(self):
        rc, lines, out = self.run_job(step("block", "true\nno-such-tool-c69"))
        self.assertEqual(self.verdicts(lines), ["unknown"], out)

    def test_exit_127_at_run_time_is_unknown(self):
        rc, lines, out = self.run_job(step("late", "sh -c 'exit 127'"))
        self.assertEqual((rc, self.verdicts(lines)), (2, ["unknown"]), out)
        self.assertIn("tool missing", lines[0])

    def test_an_action_is_not_run_locally(self):
        rc, lines, out = self.run_job(step("act", uses="actions/checkout@abc # v5"))
        self.assertEqual((rc, self.verdicts(lines)), (0, ["not run locally"]), out)
        self.assertIn("actions/checkout@abc", lines[0])
        self.assertNotIn("# v5", lines[0])

    def test_an_if_it_cannot_read_is_unknown(self):
        rc, lines, out = self.run_job(step("ref", "true", **{"if": "${{ github.ref == 'refs/heads/main' }}"}))
        self.assertEqual((rc, self.verdicts(lines)), (2, ["unknown"]), out)

    def test_an_env_expression_it_cannot_read_is_unknown(self):
        rc, lines, out = self.run_job(step("env", "true", env={"TOKEN": "${{ secrets.TOKEN }}"}))
        self.assertEqual((rc, self.verdicts(lines)), (2, ["unknown"]), out)

    def test_a_shell_it_does_not_know_is_unknown(self):
        rc, lines, out = self.run_job(step("cmd", "echo", shell="cmd"))
        self.assertEqual((rc, self.verdicts(lines)), (2, ["unknown"]), out)

    def test_a_folded_run_runs_its_text_not_the_marker(self):
        rc, lines, out = self.run_job("      - name: folded\n        run: >-\n          test -f nothing-here\n\n")
        self.assertEqual(self.verdicts(lines), ["FAIL"], out)
        self.assertFalse(os.path.exists(os.path.join(self.root, "-")), out)

    def test_a_missing_tool_inside_an_if_is_unknown(self):
        rc, lines, out = self.run_job(step("cond", "if no-such-tool-c69 --x; then echo hi; else echo no; fi"),
                                      step("neg", "while ! no-such-tool-c69; do exit 0; done"))
        self.assertEqual(self.verdicts(lines), ["unknown", "unknown"], out)

    def test_a_missing_tool_swallowed_at_run_time_is_unknown(self):
        rc, lines, out = self.run_job(step("swallowed", "t=no-such-tool-c69; $t --x || true"))
        self.assertEqual((rc, self.verdicts(lines)), (2, ["unknown"]), out)
        self.assertIn("no-such-tool-c69", lines[0])

    def test_a_heredoc_body_is_not_read_as_commands(self):
        rc, lines, out = self.run_job(step("doc", "cat > note.txt <<EOF\nno-such-word-c69 here\nEOF\ntest -s note.txt"))
        self.assertEqual((rc, self.verdicts(lines)), (0, ["PASS"]), out)

    def test_a_here_string_shift_or_quoted_marker_is_no_heredoc(self):
        for first in ("grep a <<< foo", "x=$(( 1 << 2 ))", 'echo "a <<EOF"'):
            rc, lines, out = self.run_job(step("doc", first + "\nno-such-tool-c69 2>/dev/null"))
            self.assertEqual(self.verdicts(lines), ["unknown"], first + ": " + out)

    def test_continue_on_error_is_unknown(self):
        rc, lines, out = self.run_job(step("soft", "true", continue_on_error="true"))
        self.assertEqual(self.verdicts(lines), ["unknown"], out)

    def test_a_fail_outranks_an_unknown_in_the_exit_code(self):
        rc, lines, out = self.run_job(step("tool", "no-such-tool-c69"), step("bad", "false"))
        self.assertEqual((rc, self.verdicts(lines)), (1, ["unknown", "FAIL"]), out)


class Conditions(Job):
    PR = "${{ github.event_name == 'pull_request' }}"

    def test_a_scope_flag_reads_true(self):
        cond = "${{ needs.scope.outputs.code == 'true' && needs.scope.outputs.guard == 'true' }}"
        rc, lines, out = self.run_job(step("scoped", "true", **{"if": cond}))
        self.assertEqual(self.verdicts(lines), ["PASS"], out)

    def test_not_cancelled_reads_true(self):
        cond = "${{ !cancelled() && needs.scope.outputs.mods == 'true' }}"
        rc, lines, out = self.run_job(step("last", "true", **{"if": cond}))
        self.assertEqual(self.verdicts(lines), ["PASS"], out)

    def test_a_pull_request_step_is_skipped_with_no_base(self):
        rc, lines, out = self.run_job(step("pr", "false", **{"if": self.PR}))
        self.assertEqual((rc, self.verdicts(lines)), (0, ["skipped"]), out)
        self.assertIn("--base", lines[0])

    def test_a_pull_request_step_runs_with_a_base_and_reads_base_ref(self):
        rc, lines, out = self.run_job(
            step("pr", 'test "$BASE_REF" = main && test -n "$HEAD_SHA"', **{"if": self.PR},
                 env={"BASE_REF": "${{ github.base_ref }}", "HEAD_SHA": "${{ github.event.pull_request.head.sha }}"}),
            args=("--base", "origin/main"))
        self.assertEqual(self.verdicts(lines), ["FAIL"], out)  # a repo with no commit has no HEAD sha
        subprocess.run(["git", "-C", self.root, "commit", "-q", "--allow-empty", "-m", "c"], check=True, env=ENV)
        rc, lines, out = self.run_job(
            step("pr", 'test "$BASE_REF" = main && test -n "$HEAD_SHA"', **{"if": self.PR},
                 env={"BASE_REF": "${{ github.base_ref }}", "HEAD_SHA": "${{ github.event.pull_request.head.sha }}"}),
            args=("--base", "origin/main"))
        self.assertEqual((rc, self.verdicts(lines)), (0, ["PASS"]), out)

    def test_a_not_pull_request_step_is_skipped_with_a_base(self):
        rc, lines, out = self.run_job(step("push", "false", **{"if": "${{ github.event_name != 'pull_request' }}"}),
                                      args=("--base", "origin/main"))
        self.assertEqual(self.verdicts(lines), ["skipped"], out)
        self.assertNotIn("pass --base", lines[0])


class Usage(Job):
    def test_a_job_level_env_is_unknown(self):
        path = os.path.join(self.root, "wf.yml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(workflow(step("ok", "true")).replace("    runs-on: ubuntu-latest\n", "    runs-on: ubuntu-latest\n    env:\n      A: b\n", 1))
        done = subprocess.run([sys.executable, CI_JOB, "lane", "--workflow", path], cwd=self.root,
                              capture_output=True, text=True, env=ENV)
        self.assertEqual(done.returncode, 2, done.stdout)
        self.assertIn("job-level", done.stdout)

    def test_an_absent_job_is_unknown(self):
        path = os.path.join(self.root, "wf.yml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(workflow(step("ok", "true")))
        done = subprocess.run([sys.executable, CI_JOB, "nope", "--workflow", path], cwd=self.root,
                              capture_output=True, text=True, env=ENV)
        self.assertEqual(done.returncode, 2, done.stdout)
        self.assertIn("no job", done.stdout)


class SteAction(Job):
    """The checks STE step is a `uses:` action. ci-job runs bin/ste-changed in its place (one home: run.sh)."""

    def branch_with(self, text):
        def git(*a):
            subprocess.run(["git", "-C", self.root, *a], check=True, env=ENV, capture_output=True)
        with open(os.path.join(self.root, "a.md"), "w", encoding="utf-8") as f:
            f.write("# T\n\nShort line.\n")
        git("add", ".")
        git("commit", "-qm", "base")
        git("update-ref", "refs/remotes/origin/main", "HEAD")
        git("checkout", "-qb", "lane")
        with open(os.path.join(self.root, "a.md"), "w", encoding="utf-8") as f:
            f.write("# T\n\n" + text + "\n")
        git("commit", "-qam", "change")

    def test_an_over_long_sentence_in_a_changed_md_fails_the_lint_run(self):
        self.branch_with(" ".join(["word"] * 40) + " end.")
        rc, lines, out = self.run_job(step("STE lint", uses="$/actions/ste-lint"),
                                      args=("--lint", "--base", "origin/main"))
        self.assertEqual((rc, self.verdicts(lines)), (1, ["FAIL"]), out)

    def test_a_short_sentence_in_a_changed_md_passes_the_lint_run(self):
        self.branch_with("A short sentence.")
        rc, lines, out = self.run_job(step("STE lint", uses="$/actions/ste-lint"),
                                      args=("--lint", "--base", "origin/main"))
        self.assertEqual((rc, self.verdicts(lines)), (0, ["PASS"]), out)

    def test_with_no_base_the_ste_step_runs_against_origin_main(self):
        self.branch_with(" ".join(["word"] * 40) + " end.")
        rc, lines, out = self.run_job(step("STE lint", uses="$/actions/ste-lint"), args=("--lint",))
        self.assertEqual((rc, self.verdicts(lines)), (1, ["base:", "FAIL"]), out)

    def test_another_action_is_still_not_run_locally(self):
        rc, lines, out = self.run_job(step("other", uses="actions/checkout@v4"), args=("--base", "origin/main"))
        self.assertEqual(self.verdicts(lines), ["not run locally"], out)


class LintBase(Job):
    """`--lint` with no --base must never read as a pass while CI's pull-request steps would fail."""

    PR = "${{ github.event_name == 'pull_request' }}"
    NARRATION = step("Comment narration check", 'python3 lint/check_comment_narration.py --base "origin/$BASE_REF"',
                     **{"if": PR}, env={"BASE_REF": "${{ github.base_ref }}"})

    def git(self, *a):
        subprocess.run(["git", "-C", self.root, *a], check=True, env=ENV, capture_output=True)

    def lane_adds_narration(self, origin=True):
        for rel in ("lint/check_comment_narration.py", "hooks/_nowindow.py"):
            os.makedirs(os.path.join(self.root, os.path.dirname(rel)), exist_ok=True)
            shutil.copy(os.path.join(HERE, "..", rel), os.path.join(self.root, rel))
        self.git("add", ".")
        self.git("commit", "-qm", "base")
        if origin:
            self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.git("checkout", "-qb", "lane")
        with open(os.path.join(self.root, "a.py"), "w", encoding="utf-8") as f:
            f.write("# fixed on 2026-10-28\nx = 1\n")
        self.git("add", ".")
        self.git("commit", "-qm", "change")

    def test_no_base_defaults_to_origin_main_and_the_narration_step_fails(self):
        self.lane_adds_narration()
        rc, lines, out = self.run_job(self.NARRATION, args=("--lint",))
        self.assertEqual((rc, self.verdicts(lines)), (1, ["base:", "FAIL"]), out)
        self.assertIn("origin/main (default", lines[0])

    def test_no_base_and_no_origin_main_is_unknown_and_names_the_skipped_steps(self):
        self.lane_adds_narration(origin=False)
        rc, lines, out = self.run_job(self.NARRATION, step("STE lint", uses="$/actions/ste-lint"),
                                      step("plain lint", "python3 lint/check_comment_narration.py --help"),
                                      args=("--lint",))
        self.assertEqual(rc, 2, out)
        self.assertEqual(self.verdicts(lines)[0], "unknown", out)
        self.assertIn("Comment narration check", lines[0])
        self.assertIn("STE lint", lines[0])
        self.assertNotIn("plain lint", lines[0])
        self.assertNotIn("PASS", self.verdicts(lines)[:3], out)

    def test_an_explicit_base_wins_over_the_default(self):
        self.lane_adds_narration()
        self.git("update-ref", "refs/remotes/origin/other", "HEAD")
        rc, lines, out = self.run_job(self.NARRATION, args=("--lint", "--base", "origin/other"))
        self.assertEqual((rc, self.verdicts(lines)), (0, ["PASS"]), out)
        self.assertNotIn("default", out)


class RealChecks(unittest.TestCase):
    def test_every_checks_step_gets_one_line(self):
        sys.path.insert(0, HERE)
        from workflow_steps import job_block, step_blocks
        with open(CHECKS, encoding="utf-8") as f:
            want = len(step_blocks(job_block(f.read(), "checks")))
        done = subprocess.run([sys.executable, CI_JOB, "checks", "--plan", "--base", "origin/main"],
                              cwd=os.path.join(HERE, ".."), capture_output=True, text=True, env=ENV)
        lines = [ln for ln in done.stdout.splitlines() if not ln.startswith("would fetch")]  # a shallow clone adds one
        self.assertEqual(len(lines), want, done.stdout + done.stderr)
        self.assertGreater(want, 50)
        self.assertTrue(any(ln.startswith("would run") and "STE lint" in ln for ln in lines), done.stdout)
        multi = [ln for ln in lines if "Opt-in CI template fixture suites" in ln]
        self.assertEqual(len(multi), 1, done.stdout)
        self.assertFalse(multi[0].startswith("skipped"), multi[0])


# Runs ci-job with tool lookup stubbed to find every command, so a plan reads the same with or without pipx installed.
FIND_EVERY_TOOL = ("import runpy, shutil, sys; shutil.which = lambda cmd, *a, **k: '/stub/' + cmd; "
                   "sys.argv = sys.argv[1:]; runpy.run_path(sys.argv[0], run_name='__main__')")


def plan_job(*args, cwd):
    return subprocess.run([sys.executable, "-c", FIND_EVERY_TOOL, CI_JOB, *args], cwd=cwd,
                          capture_output=True, text=True, env=ENV, timeout=60)


def plan_lint(root, wf_text, extra=()):
    """Lines of `ci-job lane --lint --plan` over a workflow text."""
    path = os.path.join(root, "wf.yml")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(wf_text)
    done = plan_job("lane", "--lint", "--plan", "--workflow", path, *extra, cwd=root)
    return done.returncode, done.stdout.splitlines(), done.stdout + done.stderr


class LintMode(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="cijob_")
        self.addCleanup(shutil.rmtree, self.root, True)
        subprocess.run(["git", "init", "-q", "-b", "main", self.root], check=True, env=ENV)

    def test_lint_mode_lists_exactly_the_lint_steps_of_checks(self):
        # An independent read: the checks job's single-line run: commands, matched by a pattern written here.
        want, name, inside = [], None, False
        with open(CHECKS, encoding="utf-8") as f:
            for line in f:
                if re.match(r"^  [\w-]+:\s*$", line):
                    inside = line.strip() == "checks:"
                if not inside:
                    continue
                m = re.match(r"^      - name: (.*?)\s*$", line)
                if m:
                    name = m.group(1)
                m = re.match(r"^        run: (python3 (?:lint|actions)/\S+\.py\b.*|bin/ste-changed\b.*|"
                             r"pipx run [\w.-]+==[\w.]+ [^|&;]*)$", line)
                if m and "mutate" not in m.group(1):
                    want.append(name)
                if re.match(r"^        uses: \S*actions/(?:ste-lint|code-check)\s*$", line):
                    want.append(name)  # a known action: ci-job runs its one home's command in its place
        self.assertGreater(len(want), 20)
        done = plan_job("checks", "--lint", "--plan", "--base", "origin/main", cwd=os.path.join(HERE, ".."))
        lines = [ln for ln in done.stdout.splitlines() if not ln.startswith("would fetch")]  # a shallow clone adds one
        self.assertEqual(len(lines), len(want), done.stdout + done.stderr)
        for expected in want:
            self.assertTrue(any(ln.split("  ", 1)[-1].startswith(expected) or ("  " + expected) in ln for ln in lines),
                            "missing %r in %s" % (expected, done.stdout))
        self.assertNotIn("test_guard", done.stdout)
        self.assertTrue({"Code check", ZIZMOR} <= set(want), want)

    def test_a_new_lint_step_is_picked_up(self):
        code, lines, out = plan_lint(self.root, workflow(
            step("old lint", "python3 lint/check_old.py"),
            step("brand new lint", "python3 lint/check_brand_new.py --strict"),
            step("new action check", "python3 actions/test_new.py"),
            step("ste", "bin/ste-changed origin/main"),
            step("noise", "true")))
        self.assertEqual(code, 0, out)
        self.assertEqual([ln.replace("would run", "", 1).strip() for ln in lines],
                         ["old lint", "brand new lint", "new action check", "ste"], out)

    def test_full_suites_and_mutation_tests_are_not_selected(self):
        code, lines, out = plan_lint(self.root, workflow(
            step("guard suite", "python3 hooks/test_guard.py"),
            step("guard suite naming lint", "python3 hooks/test_guard.py lint/x.py"),
            step("chained", "python3 hooks/test_guard.py && python3 lint/check_a.py"),
            step("lint then suite", "python3 lint/check_a.py && python3 hooks/test_guard.py"),
            step("mutation", "python3 lint/mutate_thing.py"),
            step("sweep mutation", "python3 janitor/mutate_sweep.py"),
            step("mixed block", "python3 lint/check_a.py\npython3 hooks/test_guard.py"),
            step("wrapped", "bash lint/run.sh"),
            step("kept", "python3 lint/check_a.py")))
        self.assertEqual(code, 0, out)
        self.assertEqual([ln.replace("would run", "", 1).strip() for ln in lines], ["kept"], out)


class Shallow(Job):
    """A shallow clone must get the full history CI's checkout (fetch-depth: 0) gives it."""

    def clone(self):
        origin = os.path.join(self.root, "origin")
        subprocess.run(["git", "init", "-q", "-b", "main", origin], check=True, env=ENV)
        for n in (1, 2):
            subprocess.run(["git", "-C", origin, "commit", "-q", "--allow-empty", "-m", "c%d" % n], check=True, env=ENV)
        self.work = os.path.join(self.root, "work")
        subprocess.run(["git", "clone", "-q", "--depth", "1", "file://" + origin, self.work], check=True, env=ENV)
        self.root = self.work
        return origin

    def shallow(self):
        return subprocess.run(["git", "-C", self.work, "rev-parse", "--is-shallow-repository"], capture_output=True,
                              text=True, env=ENV).stdout.strip()

    STEPS = (step("checkout", uses="actions/checkout@abc", **{"with": {"fetch-depth": "0"}}),
             step("needs history", 'test "$(git rev-parse --is-shallow-repository)" = false'))

    def test_a_shallow_clone_is_unshallowed_before_the_steps(self):
        self.clone()
        self.assertEqual(self.shallow(), "true")
        rc, lines, out = self.run_job(*self.STEPS)
        self.assertEqual(self.verdicts(lines), ["fetched", "not run locally", "PASS"], out)
        self.assertEqual((rc, self.shallow()), (0, "false"), out)

    def test_plan_only_says_it_would_fetch(self):
        self.clone()
        rc, lines, out = self.run_job(*self.STEPS, args=("--plan",))
        self.assertEqual(lines[0].split()[:2], ["would", "fetch"], out)
        self.assertEqual((rc, self.shallow()), (0, "true"), out)

    def test_a_failed_fetch_is_unknown_and_the_steps_still_run(self):
        shutil.rmtree(self.clone())
        rc, lines, out = self.run_job(*self.STEPS)
        self.assertEqual(rc, 1, out)
        self.assertTrue(lines[0].startswith("unknown") and "shallow" in lines[0], out)
        self.assertEqual(self.verdicts(lines)[1:], ["not run locally", "FAIL"], out)

    def test_a_failed_fetch_with_passing_steps_exits_two(self):
        shutil.rmtree(self.clone())
        rc, lines, out = self.run_job(self.STEPS[0], step("ok", "true"))
        self.assertEqual((rc, self.verdicts(lines)[0]), (2, "unknown"), out)

    def test_no_full_history_checkout_means_no_fetch(self):
        self.clone()
        rc, lines, out = self.run_job(step("ok", "true"))
        self.assertEqual((rc, self.verdicts(lines), self.shallow()), (0, ["PASS"], "true"), out)


def checks_step(name):
    """The checks job's step of this name, as text, so a pin is read from the workflow, never copied."""
    sys.path.insert(0, HERE)
    from workflow_steps import job_block, step_blocks, step_key
    with open(CHECKS, encoding="utf-8") as f:
        return next(st for st in step_blocks(job_block(f.read(), "checks")) if step_key(st, "name") == name) + "\n"


NO_PIPX = {"PATH": os.pathsep.join(d for d in os.environ.get("PATH", "").split(os.pathsep)
                                   if d and not os.path.exists(os.path.join(d, "pipx")))}
ZIZMOR = "Workflow supply-chain audit (zizmor)"


class LintTools(Job):
    """--lint runs checks' Code check action (code_check.py, one home) and the pinned zizmor step. A planted bug
    fails them; a missing pipx makes them unknown; neither may vanish from the lint run."""

    CODE = step("Code check", uses="$/actions/code-check", **{"with": {"base": "${{ github.event.before }}"}})
    INJECTION = ("on: issues\npermissions: {}\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n"
                 "      - run: echo \"${{ github.event.issue.title }}\"\n")
    CLEAN = "on: push\npermissions: {}\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hi\n"
    ACTION = "name: a\ndescription: a\nruns:\n  using: composite\n  steps:\n    - run: echo hi\n      shell: bash\n"

    def setUp(self):
        super().setUp()
        # CI's checkout has actions/code-check and the root ruff.toml that sets its ruff rules. A local uses: runs the
        # repo under test's own copy. The base carries both (lane commits them), so the diff under test has neither.
        shutil.copytree(os.path.join(CHECKOUT, "actions", "code-check"),
                        os.path.join(self.root, "actions", "code-check"))
        shutil.copyfile(os.path.join(CHECKOUT, "ruff.toml"), os.path.join(self.root, "ruff.toml"))

    def git(self, *a):
        subprocess.run(["git", "-C", self.root, *a], check=True, env=ENV, capture_output=True)

    def lane(self, files):
        with open(os.path.join(self.root, "base.py"), "w", encoding="utf-8") as f:
            f.write("x = 1\n")
        self.git("add", ".")
        self.git("commit", "-qm", "base")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.git("checkout", "-qb", "lane")
        for rel, text in files.items():
            os.makedirs(os.path.join(self.root, os.path.dirname(rel) or "."), exist_ok=True)
            with open(os.path.join(self.root, rel), "w", encoding="utf-8") as f:
                f.write(text)
        self.git("add", ".")
        self.git("commit", "-qm", "change")

    @unittest.skipUnless(shutil.which("pipx"), "pipx is absent: code_check.py runs its pinned ruff through pipx")
    def test_an_f541_in_a_tracked_py_fails_the_code_check(self):
        self.lane({"a.py": 'print(f"no placeholders")\n'})
        rc, lines, out = self.run_job(self.CODE, args=("--lint", "--base", "origin/main"))
        self.assertEqual((rc, self.verdicts(lines)), (1, ["FAIL"]), out)
        self.assertIn("Code check", lines[0])
        with open(self.log, encoding="utf-8") as f:
            log = f.read()
        self.assertRegex(log, r"(?m)^F541 ", out + log)  # ruff's reason, so a missing file cannot pass this case

    @unittest.skipUnless(shutil.which("pipx"), "pipx is absent: code_check.py runs its pinned ruff through pipx")
    def test_clean_python_passes_the_code_check(self):
        self.lane({"a.py": 'print("fine")\n'})
        rc, lines, out = self.run_job(self.CODE, args=("--lint", "--base", "origin/main"))
        self.assertEqual((rc, self.verdicts(lines)), (0, ["PASS"]), out)

    def test_the_code_check_with_no_pipx_is_unknown(self):
        self.lane({"a.py": 'print(f"no placeholders")\n'})
        rc, lines, out = self.run_job(self.CODE, args=("--lint", "--base", "origin/main"), env=NO_PIPX)
        self.assertEqual((rc, self.verdicts(lines)), (2, ["unknown"]), out)
        self.assertIn("pipx", lines[0])

    def test_a_tool_free_failure_with_no_pipx_still_fails_the_code_check(self):
        self.lane({"a.py": 'print("fine")\n', "b.rb": "puts 1\n"})  # no ruby row: a failure that needs no tool
        rc, lines, out = self.run_job(self.CODE, args=("--lint", "--base", "origin/main"), env=NO_PIPX)
        self.assertEqual((rc, self.verdicts(lines)), (1, ["FAIL"]), out)
        self.assertIn("could not start", lines[0])

    def test_the_code_check_with_no_base_is_skipped(self):
        rc, lines, out = self.run_job(self.CODE)
        self.assertEqual(self.verdicts(lines), ["skipped"], out)

    @unittest.skipUnless(shutil.which("pipx"), "pipx is absent: the checks zizmor step runs through pipx")
    def test_a_template_injection_fails_the_zizmor_step(self):
        self.lane({".github/workflows/bad.yml": self.INJECTION, "actions/a/action.yml": self.ACTION})
        rc, lines, out = self.run_job(checks_step(ZIZMOR), args=("--lint", "--base", "origin/main"))
        self.assertEqual((rc, self.verdicts(lines)), (1, ["FAIL"]), out)

    @unittest.skipUnless(shutil.which("pipx"), "pipx is absent: the checks zizmor step runs through pipx")
    def test_a_clean_workflow_passes_the_zizmor_step(self):
        self.lane({".github/workflows/ok.yml": self.CLEAN, "actions/a/action.yml": self.ACTION})
        rc, lines, out = self.run_job(checks_step(ZIZMOR), args=("--lint", "--base", "origin/main"))
        self.assertEqual((rc, self.verdicts(lines)), (0, ["PASS"]), out)

    def test_the_zizmor_step_with_no_pipx_is_unknown(self):
        rc, lines, out = self.run_job(checks_step(ZIZMOR), args=("--lint", "--base", "origin/main"), env=NO_PIPX)
        self.assertEqual((rc, self.verdicts(lines)), (2, ["unknown"]), out)
        self.assertIn("tool missing: pipx", lines[0])

    def test_an_unpinned_or_chained_pipx_run_is_not_a_lint_step(self):
        code, lines, out = plan_lint(self.root, workflow(step("loose", "pipx run zizmor .github/"),
                                                         step("chained", "pipx run zizmor==1.0 . && rm -rf x"),
                                                         step("pinned", "pipx run zizmor==1.0 .")))
        self.assertEqual([ln.replace("would run", "", 1).strip() for ln in lines], ["pinned"], out)

    def test_a_session_github_token_does_not_reach_a_step(self):
        rc, lines, out = self.run_job(step("offline", 'test -z "$GH_TOKEN$GITHUB_TOKEN"'),
                                      step("mapped", 'test "$GH_TOKEN" = set', env={"GH_TOKEN": "set"}),
                                      env={"GH_TOKEN": "session", "GITHUB_TOKEN": "session"})
        self.assertEqual((rc, self.verdicts(lines)), (0, ["PASS", "PASS"]), out)

    def test_an_unknown_local_action_under_lint_is_one_unknown_line(self):
        rc, lines, out = self.run_job(step("New check", uses="$/actions/new-check"),
                                      args=("--lint", "--base", "origin/main"))
        self.assertEqual((rc, self.verdicts(lines)), (2, ["unknown"]), out)
        self.assertIn("New check", lines[0])


@functools.lru_cache(maxsize=None)
def pipx_runs_pinned_ruff():
    """True when pipx can run code_check's pinned ruff. The probe is `pipx run ruff==<pin> --version`, the pin read from
    standard.json. pipx caches the tool, so only a first run downloads it. A probe over 60 s counts as no."""
    if not shutil.which("pipx"):
        return False
    with open(os.path.join(CHECKOUT, "actions", "code-check", "standard.json"), encoding="utf-8") as f:
        pin = json.load(f)["tools"]["ruff"]
    try:
        return subprocess.run(["pipx", "run", "ruff==" + pin, "--version"], capture_output=True,
                              timeout=60).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


class CodeCheckFromCopiedInstall(Job):
    """A cloud install copies bin/ci-job into ~/.claude/bin, with no symlink and no actions/ beside it. A remote uses:
    reaches code_check.py through the checkout the global rules file names, or reads unknown. A local uses: runs the
    repo under test's own code_check.py: from a copy it never borrows another checkout's, and in the repo under test
    with no actions/code-check it must FAIL."""

    # The branch builder and the git helper are LintTools' (one home): this class calls them, it does not copy them.
    git = LintTools.git
    lane = LintTools.lane
    # The remote form is the copied-install route; the local forms run the repo under test's own action.
    CODE = step("Code check", uses="shivinate7/claude-settings/actions/code-check@main")
    LOCAL_DOT = step("Code check", uses="./actions/code-check")
    LOCAL_DOLLAR = step("Code check", uses="$/actions/code-check")  # local: the form checks.yml writes
    LINT = ("--lint", "--base", "origin/main")
    # The in-repo run's tree: what ci-job imports, plus the root ruff.toml that sets ruff's rules. No actions/ and no
    # shell files, so code_check's run over the tree stays small.
    IN_REPO = ("bin/ci-job", "bin/verdict", "hooks/*.py", "lint/workflow_steps.py", "ruff.toml")

    def install(self, claude_md_checkout):
        """A copied install: ci-job and verdict as plain files, hooks/ and lint/ beside them, and a global rules file
        whose @-line names claude_md_checkout. Returns the copied ci-job and the config dir."""
        cfg = os.path.join(self.root, "cfg")
        os.makedirs(os.path.join(cfg, "bin"))
        for name in ("ci-job", "verdict"):
            shutil.copyfile(os.path.join(HERE, "..", "bin", name), os.path.join(cfg, "bin", name))
        for name in ("hooks", "lint"):
            shutil.copytree(os.path.join(CHECKOUT, name), os.path.join(cfg, name),
                            ignore=shutil.ignore_patterns("__pycache__"))
        with open(os.path.join(cfg, "CLAUDE.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("@%s/CLAUDE.md\n" % claude_md_checkout)
        return os.path.join(cfg, "bin", "ci-job"), cfg

    def test_the_code_check_step_reaches_code_check_py(self):
        if not pipx_runs_pinned_ruff():
            self.skipTest("pipx cannot run code_check's pinned ruff here: no pipx, or offline with no cached copy")
        self.lane({"a.py": 'print("fine")\n'})
        ci_job, cfg = self.install(CHECKOUT)
        rc, lines, out = self.run_job(self.CODE, args=self.LINT, script=ci_job, env={"CLAUDE_CONFIG_DIR": cfg})
        with open(self.log, encoding="utf-8") as f:
            log = f.read()
        self.assertRegex(log, r"(?m)^code-check: PASS$", out + log)  # code_check.py ran and passed the clean diff
        self.assertEqual((rc, self.verdicts(lines)), (0, ["PASS"]), out)

    def test_a_checkout_with_no_code_check_reads_unknown_not_fail(self):
        self.lane({"a.py": 'print("fine")\n'})
        empty = os.path.join(self.root, "empty-checkout")
        os.makedirs(empty)
        ci_job, cfg = self.install(empty)
        rc, lines, out = self.run_job(self.CODE, args=self.LINT, script=ci_job, env={"CLAUDE_CONFIG_DIR": cfg})
        self.assertEqual((rc, self.verdicts(lines)), (2, ["unknown"]), out)
        self.assertIn("code_check.py", lines[0], out)

    def test_an_in_repo_run_with_no_code_check_fails_and_never_borrows_a_pointer_copy(self):
        tar = self.root + ".tar"
        subprocess.run(["git", "archive", "--format=tar", "-o", tar, "HEAD", "--", *self.IN_REPO], cwd=CHECKOUT,
                       check=True, env=ENV)
        subprocess.run(["tar", "-xf", tar, "-C", self.root], check=True)  # the repo under test: no actions/ in it
        self.lane({"a.py": 'print("fine")\n'})
        cfg = tempfile.mkdtemp(prefix="cfg-", dir=RUN_FOLDER)
        with open(os.path.join(cfg, "CLAUDE.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("@%s/CLAUDE.md\n" % CHECKOUT)  # a checkout that does have actions/code-check
        rc, lines, out = self.run_job(self.LOCAL_DOT, args=self.LINT, script=os.path.join(self.root, "bin", "ci-job"),
                                      env={"CLAUDE_CONFIG_DIR": cfg})
        with open(self.log, encoding="utf-8") as f:
            log = f.read()
        self.assertEqual((rc, self.verdicts(lines)), (1, ["FAIL"]), out + log)
        self.assertNotRegex(log, r"(?m)^code-check: ", out + log)  # the pointer copy's code_check never ran
        self.assertIn("code_check.py", log, out + log)  # main's reason: the in-repo file is not there

    def test_a_local_uses_from_a_copy_fails_on_the_repos_own_failing_code_check(self):
        self.lane({"actions/code-check/code_check.py": "raise SystemExit(1)\n", "a.py": 'print("fine")\n'})
        ci_job, cfg = self.install(CHECKOUT)  # a copy outside the repo; the rules file names a good checkout
        rc, lines, out = self.run_job(self.LOCAL_DOLLAR, args=self.LINT, script=ci_job,
                                      env={"CLAUDE_CONFIG_DIR": cfg})
        with open(self.log, encoding="utf-8") as f:
            log = f.read()
        self.assertEqual((rc, self.verdicts(lines)), (1, ["FAIL"]), out + log)
        self.assertNotRegex(log, r"(?m)^code-check: ", out + log)  # the good copy's code_check never ran


@unittest.skipUnless(os.name == "posix", "the stall watch and the process-group check are posix only")
class QuietStepKeepsTheStallWatchFed(Job):
    """A step quiet past the stall limit must not strand its job. verdict's heartbeat has to reach ci-job's own
    output, so the stall watch sees the job alive. The job then ends on its own, with no process of it left."""

    QUIET = step("quiet", "sleep 6")
    SLOW = step("slow", "sleep 2.5")

    def start_job(self, *steps, env):
        """Start ci-job, stdout and stderr to one file, in its own process group that cleanup alone kills."""
        argv, env = self.job_call(*steps, env=env)
        handle = open(os.path.join(self.root, "job.out"), "wb")
        self.addCleanup(handle.close)
        proc = subprocess.Popen(argv, cwd=self.root, env=env, stdout=handle, stderr=subprocess.STDOUT,
                                start_new_session=True)
        self.addCleanup(self.kill_group, proc)
        return proc, handle.name

    @staticmethod
    def kill_group(proc):
        try:
            os.killpg(proc.pid, signal.SIGKILL)  # the group ci-job started: its own jobs and nothing else
        except ProcessLookupError:
            pass
        proc.wait()

    def test_a_quiet_step_does_not_trip_the_stall_watch(self):
        proc, out = self.start_job(self.QUIET, env={"VERDICT_HEARTBEAT": "1"})
        watch = subprocess.run([sys.executable, STALL_WATCH, "--watch-pid", str(proc.pid), "--log", out,
                                "--quiet", "3"], capture_output=True, text=True, timeout=60)
        with open(out, encoding="utf-8", errors="replace") as f:
            job_out = f.read()
        self.assertEqual(watch.returncode, 0, watch.stdout + watch.stderr + job_out)
        proc.wait(timeout=60)  # reap the job: it has ended on its own
        with self.assertRaises(ProcessLookupError, msg="a process of the job is still running"):
            os.killpg(proc.pid, 0)

    def test_stdout_keeps_one_verdict_line_and_stderr_gets_the_heartbeat(self):
        argv, env = self.job_call(self.SLOW, env={"VERDICT_HEARTBEAT": "1"})
        done = subprocess.run(argv, cwd=self.root, capture_output=True, text=True, env=env, timeout=120)
        lines = [ln for ln in done.stdout.splitlines() if not ln.startswith("log=")]
        self.assertEqual((done.returncode, self.verdicts(lines)), (0, ["PASS"]), done.stdout + done.stderr)
        self.assertNotIn("still running", done.stdout)
        self.assertIn("still running", done.stderr, done.stdout + done.stderr)


if __name__ == "__main__":
    try:
        unittest.main()
    finally:
        shutil.rmtree(RUN_FOLDER, ignore_errors=True)
