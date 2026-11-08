#!/usr/bin/env python3
"""Fixture suite for bin/ci-job: each case writes a workflow into a throwaway repo and runs one job.

Red cases: a multi-line step whose last line fails, a missing tool (named, behind xargs, or exit 127),
a `uses:` step, an `if:` or env expression the runner cannot read, and a pull-request step with no base.
None of them may read PASS. The GithubBaseRef class: the GITHUB_BASE_REF each step gets from --base, unset with none.
The last class plans the real checks job: every step gets one line.
The last two classes: the code-check step from a copied install, and a step quiet past the stall limit.
StepMaps reads a step's with: and env: values: a block scalar as its lines, an inline comment dropped.
StepSelect: --step runs only the named steps; a name no step has is one unknown line, exit 2.
PinnedSettings: --step runs each named step in the claude-settings tree the workflow pins (one distinct 40-hex sha on its
`<owner>/claude-settings/actions/<name>@<ref>` uses: lines); two pins, a ref that is no sha, or an unfetchable sha is unknown.
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
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: every temp path comes from this run's folder
from workflow_steps import run_body, step_blocks, step_env, step_with  # noqa: E402  the one home of the step parser
RUN_FOLDER = _test_temp.run_folder()
CHECKOUT = os.path.abspath(os.path.join(HERE, ".."))
CI_JOB = os.path.join(HERE, "..", "bin", "ci-job")
CHECKS = os.path.join(HERE, "..", ".github", "workflows", "checks.yml")
WORKFLOWS = os.path.join(HERE, "..", ".github", "workflows")
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


SUMMARY = re.compile(r"^summary: (?:ran|would run) \d+ of \d+ steps$")  # the last line of a --lint run or plan; merge.py reads `would run ` lines, so it never starts with one
SUMMARY_ANY = re.compile(r"^(?:summary: )?(?:ran|would run) \d+ of \d+ steps$")  # the prefix is checked elsewhere: step helpers skip either form
NOT_RUN = re.compile(r"^not run(?! locally)\b")  # a step --lint does not run: its own line, never a verdict


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
        return [ln.split()[0] if not ln.startswith("not run locally") else "not run locally" for ln in lines
                if not NOT_RUN.match(ln) and not SUMMARY.match(ln)]  # a --lint run's not-run and summary lines are no verdict


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
    """A step that skips tests reads SKIP, never PASS, and never hides a FAIL (plan row S8, test-ci-standard plan)."""

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

    def test_a_scope_flag_not_equal_to_false_reads_true(self):
        rc, lines, out = self.run_job(step("flag", "true", **{"if": "${{ needs.scope.outputs.code != 'false' }}"}))
        self.assertEqual((rc, self.verdicts(lines)), (0, ["PASS"]), out)

    def test_a_scope_flag_not_equal_to_false_and_a_pull_request_is_skipped_with_no_base(self):
        cond = "${{ needs.scope.outputs.code != 'false' && github.event_name == 'pull_request' }}"
        rc, lines, out = self.run_job(step("pr flag", "false", **{"if": cond}))
        self.assertEqual((rc, self.verdicts(lines)), (0, ["skipped"]), out)

    def test_a_scope_flag_equal_to_false_reads_unknown(self):
        rc, lines, out = self.run_job(step("flag", "true", **{"if": "${{ needs.scope.outputs.code == 'false' }}"}))
        self.assertEqual((rc, self.verdicts(lines)), (2, ["unknown"]), out)

    def test_a_scope_flag_not_equal_to_true_reads_unknown(self):
        rc, lines, out = self.run_job(step("flag", "true", **{"if": "${{ needs.scope.outputs.code != 'true' }}"}))
        self.assertEqual((rc, self.verdicts(lines)), (2, ["unknown"]), out)

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


class StepSelect(Job):
    """`--step NAME` (repeatable) runs only the named steps of the job, of any kind. A name no step has is one unknown
    line and exit 2. The merge's ready checks run its declared names this way (merge.readyChecks)."""
    PR = Conditions.PR  # the one home of the pull-request condition

    def test_only_the_named_steps_run_and_the_others_do_not(self):
        rc, lines, out = self.run_job(step("first", "echo first > first.txt"),
                                      step("second", "echo second > second.txt\nexit 1"),
                                      step("third", "echo third > third.txt"),
                                      args=("--step", "first", "--step", "third"))
        self.assertTrue(os.path.exists(os.path.join(self.root, "first.txt")), out)
        self.assertTrue(os.path.exists(os.path.join(self.root, "third.txt")), out)
        self.assertFalse(os.path.exists(os.path.join(self.root, "second.txt")), out)
        self.assertEqual((rc, self.verdicts(lines)), (0, ["PASS", "PASS"]), out)

    def test_a_name_no_step_has_is_one_unknown_line_and_exit_two(self):
        rc, lines, out = self.run_job(step("ok", "echo ran > ran.txt"), args=("--step", "nope"))
        self.assertEqual(self.verdicts(lines), ["unknown"], out)
        self.assertIn("nope", lines[0], out)
        self.assertEqual(rc, 2, out)
        self.assertFalse(os.path.exists(os.path.join(self.root, "ran.txt")), out)

    def test_a_named_uses_step_is_one_unknown_line_and_exit_two(self):
        rc, lines, out = self.run_job(step("ok", "echo ran > ran.txt"), step("act", uses="actions/checkout@v4"),
                                      args=("--step", "act"))
        self.assertEqual(self.verdicts(lines), ["unknown"], out)
        self.assertIn("act", lines[0], out)
        self.assertEqual(rc, 2, out)
        self.assertFalse(os.path.exists(os.path.join(self.root, "ran.txt")), out)

    def test_a_named_pull_request_step_with_no_base_is_one_unknown_line_and_exit_two(self):
        rc, lines, out = self.run_job(step("pr", "echo pr > pr.txt", **{"if": self.PR}), args=("--step", "pr"))
        self.assertEqual(self.verdicts(lines), ["unknown"], out)
        self.assertEqual(rc, 2, out)
        self.assertFalse(os.path.exists(os.path.join(self.root, "pr.txt")), out)

    def test_a_run_with_no_step_runs_every_step(self):  # the control
        rc, lines, out = self.run_job(step("one", "true"), step("two", "true"))
        self.assertEqual((rc, self.verdicts(lines)), (0, ["PASS", "PASS"]), out)


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
        for rel in ("lint/check_comment_narration.py", "hooks/_nowindow.py", "actions/code-check/standard.json"):
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


class GithubBaseRef(Job):
    """A pull-request run sets GITHUB_BASE_REF in each step's env, as the Actions runner does: the base without its
    remote. With no base there is no pull-request run, so the variable is unset even when the caller's env sets it.
    ci-job relays no step output, so each step writes the value it sees to seen.txt. `<unset>` is no ref name."""

    SEEN = "printf '%s' \"${GITHUB_BASE_REF-<unset>}\" > seen.txt"

    def seen_after(self, *steps, args=(), env=None):
        """(verdicts, the value the step wrote or a note that it wrote none, output) of one run of the job."""
        path = os.path.join(self.root, "seen.txt")
        if os.path.exists(path):
            os.remove(path)
        rc, lines, out = self.run_job(*steps, args=args, env=env)
        if not os.path.exists(path):
            return self.verdicts(lines), "(no seen.txt: the step did not run)", out
        with open(path, encoding="utf-8") as f:
            return self.verdicts(lines), f.read(), out

    def test_a_pull_request_run_sets_github_base_ref_to_the_base_without_its_remote(self):
        verdicts, seen, out = self.seen_after(step("seen", self.SEEN), args=("--base", "origin/main"))
        self.assertEqual((verdicts, seen), (["PASS"], "main"), out)

    def test_the_base_keeps_every_slash_after_its_remote(self):
        verdicts, seen, out = self.seen_after(step("seen", self.SEEN), args=("--base", "origin/release/1.2"))
        self.assertEqual((verdicts, seen), (["PASS"], "release/1.2"), out)

    def test_a_base_replaces_a_github_base_ref_the_caller_set(self):
        verdicts, seen, out = self.seen_after(step("seen", self.SEEN), args=("--base", "origin/main"),
                                              env={"GITHUB_BASE_REF": "stale"})
        self.assertEqual((verdicts, seen), (["PASS"], "main"), out)

    def test_a_step_env_that_sets_github_base_ref_wins_over_the_base(self):
        verdicts, seen, out = self.seen_after(step("seen", self.SEEN, env={"GITHUB_BASE_REF": "from-step"}),
                                              args=("--base", "origin/main"))
        self.assertEqual((verdicts, seen), (["PASS"], "from-step"), out)

    def test_with_no_base_github_base_ref_is_unset_even_when_the_caller_sets_it(self):
        verdicts, seen, out = self.seen_after(step("seen", self.SEEN), env={"GITHUB_BASE_REF": "stale"})
        self.assertEqual((verdicts, seen), (["PASS"], "<unset>"), out)

    def test_a_lint_run_with_a_base_sets_github_base_ref_for_its_lint_steps(self):
        os.makedirs(os.path.join(self.root, "lint"))
        with open(os.path.join(self.root, "lint", "seen_base_ref.py"), "w", encoding="utf-8") as f:
            f.write("import os\nopen('seen.txt', 'w', encoding='utf-8').write(os.environ.get('GITHUB_BASE_REF', '<unset>'))\n")
        verdicts, seen, out = self.seen_after(step("seen", "python3 lint/seen_base_ref.py"),
                                              args=("--lint", "--base", "origin/main"))
        self.assertEqual((verdicts, seen), (["PASS"], "main"), out)


def mapped(parent, body):
    """One `      - ` step whose `parent:` block (`with` or `env`) holds `body`, raw, as YAML writes it."""
    return "      - name: s\n        %s:\n%s\n" % (parent, body)


def words_of(mapping, key):
    """The words of mapping[key], as run.sh splits a paths value; [] when the key is absent."""
    return mapping.get(key, "").split()


class StepMaps(unittest.TestCase):
    """A step's with: and env: values as lint/workflow_steps.py reads them for bin/ci-job. A block scalar (`|`, `>`,
    `|-`) reads as its lines. An inline comment (a space, then `#`) is not part of the value. A `#` inside quotes or
    inside a block scalar is text."""

    def test_a_literal_block_reads_its_lines(self):
        value = step_with(mapped("with", "          paths: |\n            a/\n            b/\n"))
        self.assertEqual(words_of(value, "paths"), ["a/", "b/"], "with: paths: | was read as its marker, not its lines")

    def test_a_folded_block_reads_its_lines(self):
        value = step_with(mapped("with", "          paths: >\n            a/\n            b/\n"))
        self.assertEqual(words_of(value, "paths"), ["a/", "b/"], "with: paths: > was read as its marker, not its lines")

    def test_a_chomping_block_reads_its_lines(self):
        value = step_with(mapped("with", "          paths: |-\n            a/\n            b/\n"))
        self.assertEqual(words_of(value, "paths"), ["a/", "b/"], "with: paths: |- was read as its marker, not its lines")

    def test_an_empty_block_reads_as_no_words(self):
        value = step_with(mapped("with", "          paths: |\n"))
        self.assertEqual(words_of(value, "paths"), [], "an empty with: paths: | block read its marker as a path")

    def test_an_inline_comment_is_not_part_of_the_value(self):
        value = step_with(mapped("with", "          paths: .github/ # audit\n"))
        self.assertEqual(value.get("paths"), ".github/", "the inline comment stayed in the with: paths value")

    def test_a_comment_after_a_quoted_value_is_dropped_and_a_hash_inside_quotes_is_kept(self):
        value = step_with(mapped("with", '          paths: "a/ # b/" # audit\n'))
        self.assertEqual(value.get("paths", "").strip("'\""), "a/ # b/", "the inline comment stayed in the with: paths value")

    def test_a_hash_with_no_space_before_it_is_text(self):
        value = step_with(mapped("with", "          paths: a/#b # note\n"))
        self.assertEqual(value.get("paths"), "a/#b", "the inline comment stayed in the with: paths value")

    def test_a_lone_quote_in_text_is_kept(self):
        value = step_with(mapped("with", "          paths: don't/ # note\n"))
        self.assertEqual(value.get("paths"), "don't/", "the inline comment stayed in the with: paths value")

    def test_a_hash_inside_a_block_is_text(self):
        value = step_with(mapped("with", "          paths: |\n            a/ # kept\n"))
        self.assertEqual(words_of(value, "paths"), ["a/", "#", "kept"], "a # inside a with: paths block was dropped")

    def test_an_env_literal_block_reads_its_lines(self):
        value = step_env(mapped("env", "          ZIZMOR_PATHS: |\n            a/\n            b/\n"))
        self.assertEqual(words_of(value, "ZIZMOR_PATHS"), ["a/", "b/"], "env: ZIZMOR_PATHS: | was read as its marker")

    def test_an_env_inline_comment_is_not_part_of_the_value(self):
        value = step_env(mapped("env", "          NOTE: x # y\n"))
        self.assertEqual(value.get("NOTE"), "x", "the inline comment stayed in the env: NOTE value")

    def test_an_env_literal_block_value_is_exact(self):
        value = step_env(mapped("env", "          MSG: |\n            hello\n"))
        self.assertEqual(value.get("MSG"), "hello\n", "a literal env: block kept a space from its indent")

    def test_an_env_literal_block_keeps_extra_indent_on_a_later_line(self):
        value = step_env(mapped("env", "          MSG: |\n            hello\n              world\n"))
        self.assertEqual(value.get("MSG"), "hello\n  world\n", "a literal env: block lost or added indent on a later line")

    def test_an_env_literal_block_keeps_a_blank_line(self):
        value = step_env(mapped("env", "          MSG: |\n            hello\n\n            world\n"))
        self.assertEqual(value.get("MSG"), "hello\n\nworld\n", "a literal env: block lost its blank line")

    def test_an_env_strip_block_drops_the_final_newline(self):
        value = step_env(mapped("env", "          X: |-\n            a\n"))
        self.assertEqual(value.get("X"), "a", "env: X: |- kept the final newline its header strips")

    def test_a_with_folded_block_value_is_exact(self):
        value = step_with(mapped("with", "          paths: >\n            a/\n            b/\n\n            c/\n"))
        self.assertEqual(value.get("paths"), "a/ b/\nc/\n", "with: paths: > is not folded as YAML folds it")

    def test_a_quoted_value_with_an_escaped_quote_keeps_its_hash_and_drops_the_comment(self):
        value = step_env(mapped("env", '          MSG: "a \\" # b" # c\n'))
        self.assertEqual(value.get("MSG"), '"a \\" # b"', "the quoted env: value was cut at its inner # or kept the comment")

    def test_a_single_quoted_value_with_a_doubled_quote_keeps_its_hash_and_drops_the_comment(self):
        value = step_env(mapped("env", "          MSG: 'it''s # x' # y\n"))
        self.assertEqual(value.get("MSG"), "'it''s # x'", "the quoted env: value was cut at its inner # or kept the comment")


def run_as_yaml_reads_it(step):
    """(kind, text) of a step's run: as YAML reads it. A literal `run: |` body is its lines indented 10 or more, or
    blank, with the 10 spaces removed, the blank lines at each end dropped, and one final newline. A one-line run is its
    text. kind is None when the step has no run:, and "other" for a header this reading does not cover."""
    lines = step.split("\n")
    for i, line in enumerate(lines):
        m = re.match(r"^(?:      - |        )run:[ \t]*(.*?)[ \t]*$", line)
        if not m:
            continue
        head = m.group(1)
        if not head.startswith(("|", ">")):
            return "line", head
        if head != "|":
            return "other", None
        body = []
        for ln in lines[i + 1:]:
            if ln.strip() and not ln.startswith(" " * 10):
                break
            body.append(ln[10:] if ln.strip() else "")
        while body and not body[0]:
            body.pop(0)
        while body and not body[-1]:
            body.pop()
        return "literal", "\n".join(body) + "\n"
    return None, None


class RunBodiesOfWorkflows(unittest.TestCase):
    """run_body reads each run: block of the repo's workflows as YAML reads it. The reading is written out in
    run_as_yaml_reads_it, from the YAML definition, so a change to run_body's text for a real workflow fails here."""

    def test_every_workflow_run_block_reads_as_yaml_reads_it(self):
        literal = 0
        for name in sorted(os.listdir(WORKFLOWS)):
            if not name.endswith(".yml"):
                continue
            with open(os.path.join(WORKFLOWS, name), encoding="utf-8") as f:
                text = f.read()
            for step in step_blocks(text):
                kind, expected = run_as_yaml_reads_it(step)
                if kind is None:
                    continue
                self.assertNotEqual(kind, "other", "%s: a run: header this reading does not cover" % name)
                literal += kind == "literal"
                self.assertEqual(run_body(step), expected, "%s: run_body's text for a run: block changed" % name)
        self.assertGreater(literal, 0, "no literal run: block was read, so the check covered nothing")


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
                if re.match(r"^        uses: \S*actions/(?:ste-lint|code-check|zizmor)\s*$", line):
                    want.append(name)  # a known action: ci-job runs its one home's command in its place
        self.assertGreater(len(want), 20)
        done = plan_job("checks", "--lint", "--plan", "--base", "origin/main", cwd=os.path.join(HERE, ".."))
        lines = [ln for ln in done.stdout.splitlines() if ln.startswith("would run ") and not SUMMARY.match(ln)]
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
        self.assertEqual(selected(lines), ["old lint", "brand new lint", "new action check", "ste"], out)

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
        self.assertEqual(selected(lines), ["kept"], out)


LINT_SCRIPT = ("import os, sys\n"
               "open('lint-ran.txt', 'w').close()\n"
               "if not os.path.exists('installed.marker'):\n"
               "    print('install marker missing: the install step did not run before this lint step')\n"
               "    sys.exit(1)\n")
VERDICT_WORDS = ("would run", "not run locally", "not run", "skipped", "unknown", "PASS", "SKIP", "FAIL")


def by_step(lines):
    """{step name: verdict word} from a job's lines: each line is a verdict word, the step's name, then ': detail'.
    The summary line names no step, so it is no entry."""
    found = {}
    for ln in lines:
        word = next((w for w in VERDICT_WORDS if ln.startswith(w + " ")), None)
        if word and not SUMMARY_ANY.match(ln):
            found[ln[len(word):].strip().split(": ", 1)[0]] = word
    return found


def would_run(lines):
    """The sorted names of the steps a --lint plan would run."""
    return sorted(name for name, word in by_step(lines).items() if word == "would run")


def selected(lines):
    """Each `would run` line's step name, in order. The summary line is not one."""
    return [ln.replace("would run", "", 1).strip() for ln in lines
            if ln.startswith("would run ") and not SUMMARY.match(ln)]


class InstallSteps(Job):
    """--lint runs a job's install steps before the lint steps after them. An install step is a run: whose every line
    is one lockfile install or framework type generation. A failed install is unknown, never FAIL, and the lint steps
    after it do not run. npm and npx are stubs on a temp PATH, so no case reaches the network."""

    LINT = "python3 lint/check_installed.py"
    INSTALL_FORMS = ("npm ci", "pnpm install --frozen-lockfile", "yarn install --frozen-lockfile", "yarn install --immutable",
                     "pip install -r requirements.txt", "python3 -m pip install -r requirements.txt",
                     "npx astro sync", "npx --no-install astro sync", "npx astro generate")
    NOT_INSTALL_FORMS = ("npm run build", "npx eslint .", "npx astro check", "pip install requests",
                         "pip install -r req.txt&&python3 lint/x.py", "npm ci;echo hi", "pip install -r a.txt|tee x",
                         "npx astro sync&&curl x")
    NPM_OK = 'touch installed.marker\necho "$*" >> npm-calls.txt'

    def setUp(self):
        super().setUp()
        os.makedirs(os.path.join(self.root, "lint"))
        with open(os.path.join(self.root, "lint", "check_installed.py"), "w", encoding="utf-8", newline="\n") as f:
            f.write(LINT_SCRIPT)

    def stub_path(self, **tools):
        """PATH with each named tool first, as a shell script that runs its body."""
        bin_dir = os.path.join(self.root, "stubs")
        os.makedirs(bin_dir, exist_ok=True)
        for name, body in tools.items():
            path = os.path.join(bin_dir, name)
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write("#!/bin/sh\n" + body + "\n")
            os.chmod(path, 0o755)
        return {"PATH": os.pathsep.join([bin_dir, os.environ.get("PATH", "")])}

    def npm_calls(self):
        """What the npm stub recorded, or a note that it recorded nothing."""
        try:
            with open(os.path.join(self.root, "npm-calls.txt"), encoding="utf-8") as f:
                return f.read()
        except OSError:
            return "(no npm call)"

    def test_a_lockfile_install_runs_before_the_lint_step_that_needs_it(self):
        env = self.stub_path(npm=self.NPM_OK)
        rc, lines, out = self.run_job(step("Install deps", "npm ci"), step("Lint check", self.LINT),
                                      args=("--lint",), env=env)
        self.assertEqual(by_step(lines).get("Lint check"), "PASS",
                         "the lint step failed: the install step before it did not run\n" + out)
        self.assertEqual((rc, self.npm_calls()), (0, "ci\n"), out)

    def test_a_failed_install_is_unknown_and_each_lint_step_after_it_is_unknown_and_does_not_run(self):
        env = self.stub_path(npm='echo "npm: stub install failed" >&2\nexit 1')
        rc, lines, out = self.run_job(step("Install deps", "npm ci"), step("Lint one", self.LINT),
                                      step("Lint two", self.LINT), args=("--lint",), env=env)
        self.assertEqual((rc, by_step(lines)), (2, {"Install deps": "unknown", "Lint one": "unknown",
                                                    "Lint two": "unknown"}), out)
        for ln in lines:
            if "Lint one" in ln or "Lint two" in ln:
                self.assertIn("Install deps", ln, "a lint line does not name the failed install\n" + out)
        self.assertFalse(os.path.exists(os.path.join(self.root, "lint-ran.txt")),
                         "a lint step ran after its install failed\n" + out)

    def test_a_framework_type_generation_is_selected_under_lint_plan(self):
        code, lines, out = plan_lint(self.root, workflow(step("Astro types", "npx astro sync"),
                                                         step("Lint check", self.LINT)))
        self.assertEqual((code, would_run(lines)), (0, ["Astro types", "Lint check"]), out)

    def test_every_install_form_the_goal_names_is_selected_under_lint_plan(self):
        got = {}
        for form in self.INSTALL_FORMS:
            got[form] = would_run(plan_lint(self.root, workflow(step("Install deps", form), step("Lint check", self.LINT)))[1])
        self.assertEqual(got, {form: ["Install deps", "Lint check"] for form in self.INSTALL_FORMS},
                         "an install form is not selected under --lint --plan")

    def test_a_command_outside_the_install_forms_is_not_selected_under_lint_plan(self):
        got = {}
        for form in self.NOT_INSTALL_FORMS:
            got[form] = would_run(plan_lint(self.root, workflow(step("Other", form), step("Lint check", self.LINT)))[1])
        self.assertEqual(got, {form: ["Lint check"] for form in self.NOT_INSTALL_FORMS},
                         "a command that is no install form is selected under --lint --plan")

    def test_a_step_that_mixes_an_install_with_another_line_is_not_selected(self):
        code, lines, out = plan_lint(self.root, workflow(step("Mixed", 'npm ci\necho done >> "$GITHUB_PATH"'),
                                                         step("Lint check", self.LINT)))
        self.assertEqual((code, would_run(lines)), (0, ["Lint check"]), out)

    def test_an_install_whose_only_later_lint_step_is_skipped_does_not_run(self):
        env = self.stub_path(npm=self.NPM_OK)
        _, lines, out = self.run_job(
            step("Install deps", "npm ci"),
            step("Lint check", self.LINT, **{"if": "${{ github.event_name == 'pull_request' }}"}),
            args=("--lint",), env=env)
        self.assertEqual(by_step(lines).get("Lint check"), "skipped", out)
        self.assertFalse(os.path.exists(os.path.join(self.root, "installed.marker")),
                         "the install ran though no lint step after it runs\n" + out)


class NotRunLines(Job):
    """--lint prints one `not run` line for each step it does not run, then a summary: how many of the job's steps ran.
    --plan with --lint prints the same lines with `would run`. Neither changes the exit code, and no not-run line reads
    as FAIL or unknown, the two words merge.py's lane lint reads."""

    DEGEN = (step("Checkout", uses="actions/checkout@v4"),
             step("Setup node", uses="actions/setup-node@v4"),
             step("Python lint", "python3 lint/check_clean.py"),
             step("Make lint-py", "make lint-py"),
             step("Make gen-check", "make gen-check"))
    EXPECTED_NOT_RUN = ["Checkout", "Make gen-check", "Make lint-py", "Setup node"]

    def setUp(self):
        super().setUp()
        os.makedirs(os.path.join(self.root, "lint"))
        for name, body in (("check_clean.py", "print('clean')\n"),
                           ("check_fails.py", "import sys\nprint('lint fails')\nsys.exit(1)\n")):
            with open(os.path.join(self.root, "lint", name), "w", encoding="utf-8", newline="\n") as f:
                f.write(body)

    def test_under_lint_each_step_not_run_gets_a_line_and_the_summary_counts_the_run_ones(self):
        rc, lines, out = self.run_job(*self.DEGEN, args=("--lint",))
        self.assertEqual(by_step(lines), {"Checkout": "not run", "Setup node": "not run", "Python lint": "PASS",
                                          "Make lint-py": "not run", "Make gen-check": "not run"}, out)
        self.assertIn("summary: ran 1 of 5 steps", lines, out)

    def test_plan_under_lint_prints_the_same_not_run_lines_with_would_run_counts(self):
        code, lines, out = plan_lint(self.root, workflow(*self.DEGEN))
        self.assertEqual((code, by_step(lines)), (0, {"Checkout": "not run", "Setup node": "not run",
                                                      "Python lint": "would run", "Make lint-py": "not run",
                                                      "Make gen-check": "not run"}), out)
        self.assertIn("summary: would run 1 of 5 steps", lines, out)
        would = [ln for ln in lines if ln.startswith("would run ")]  # what merge.py's lint_steps reads
        self.assertEqual(len(would), 1, "the summary line is read as a step: " + "; ".join(would))

    def test_not_run_lines_leave_the_exit_code_and_never_read_as_fail_or_unknown(self):
        rc, lines, out = self.run_job(*self.DEGEN, args=("--lint",))
        self.assertEqual(sorted(n for n, word in by_step(lines).items() if word == "not run"), self.EXPECTED_NOT_RUN, out)
        self.assertEqual(rc, 0, out)
        self.assertEqual([ln for ln in lines if ln.startswith(("FAIL", "unknown"))], [], out)
        rc, lines, out = self.run_job(step("Checkout", uses="actions/checkout@v4"), step("Make lint-py", "make lint-py"),
                                      step("Python lint", "python3 lint/check_fails.py"), args=("--lint",))
        self.assertEqual((rc, by_step(lines)), (1, {"Checkout": "not run", "Make lint-py": "not run",
                                                    "Python lint": "FAIL"}), out)


class Progress(Job):
    """Each step ci-job runs prints one `start:` line to stderr before it runs, and none to stdout: a caller that reads
    stdout for the verdicts keeps its lines, and a long run shows which step it is on. Each step greps the stderr file
    itself, so its start line must already be there when the step runs."""

    def test_each_run_step_announces_itself_on_stderr_before_it_runs(self):
        err_path = os.path.join(self.root, "stderr.txt")
        argv, env = self.job_call(step("First", 'grep -q "start.*First" "$ERR_FILE"'),
                                  step("Second", 'grep -q "start.*Second" "$ERR_FILE"'),
                                  env={"ERR_FILE": err_path})
        with open(err_path, "w", encoding="utf-8") as err:
            done = subprocess.run(argv, cwd=self.root, stdout=subprocess.PIPE, stderr=err, text=True, env=env, timeout=120)
        with open(err_path, encoding="utf-8") as f:
            err_text = f.read()
        lines = [ln for ln in done.stdout.splitlines() if not ln.startswith("log=")]
        self.assertEqual((done.returncode, self.verdicts(lines)), (0, ["PASS", "PASS"]), done.stdout + err_text)
        self.assertEqual([ln for ln in lines if ln.startswith("start")], [], done.stdout)
        starts = [ln for ln in err_text.splitlines() if ln.startswith("start:")]
        self.assertEqual(len(starts), 2, "the stderr holds %d start lines, want one per run step: %s" % (len(starts), err_text))
        self.assertIn("First", starts[0], err_text)
        self.assertIn("Second", starts[1], err_text)


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
    """--lint runs checks' Code check action (code_check.py, one home) and the zizmor action (actions/zizmor/run.sh,
    one home of the pin). A planted bug fails them; a missing pipx makes them unknown; neither may vanish from the lint
    run."""

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
        shutil.copytree(os.path.join(CHECKOUT, "actions", "zizmor"), os.path.join(self.root, "actions", "zizmor"))
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

    def run_with_stub_pipx(self, *steps):
        """Runs one job under --lint with a stub pipx first on PATH. The stub writes its argv, one word a line, to a file.
        Returns (rc, lines, out, argv): argv is None when pipx was never called."""
        bin_dir = tempfile.mkdtemp(prefix="pipx_", dir=RUN_FOLDER)
        argv_file = os.path.join(bin_dir, "argv.txt")
        with open(os.path.join(bin_dir, "pipx"), "w", encoding="utf-8", newline="\n") as f:
            f.write("#!/bin/sh\nprintf '%%s\\n' \"$@\" > '%s'\n" % argv_file)
        os.chmod(os.path.join(bin_dir, "pipx"), 0o755)
        env = {"PATH": os.pathsep.join([bin_dir, os.environ.get("PATH", "")])}
        rc, lines, out = self.run_job(*steps, args=("--lint",), env=env)
        argv = None
        if os.path.exists(argv_file):
            with open(argv_file, encoding="utf-8") as f:
                argv = f.read().splitlines()
        return rc, lines, out, argv

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

    def test_the_zizmor_action_under_lint_runs_with_no_base(self):
        # A literal uses: step, not checks_step(ZIZMOR): checks.yml's step has the run: form on this branch, and the
        # old run: path needs no base, so it could not show red here. The fixture has no origin/main, so no base resolves.
        no_main = subprocess.run(["git", "-C", self.root, "rev-parse", "--verify", "-q", "origin/main"],
                                 env=ENV, capture_output=True)
        self.assertNotEqual(no_main.returncode, 0, "the fixture must have no origin/main, so no base resolves")
        rc, lines, out, argv = self.run_with_stub_pipx(
            step(ZIZMOR, uses="$/actions/zizmor", **{"with": {"paths": ".github/ actions/"}}))
        self.assertEqual((rc, self.verdicts(lines)), (0, ["PASS"]), out)
        self.assertIsNotNone(argv, "pipx was never called, so the action did not run zizmor\n" + out)
        self.assertEqual(argv[0], "run", out)
        self.assertEqual(argv[2:], [".github/", "actions/"], out)

    def test_a_zizmor_paths_block_passes_each_path_to_pipx(self):
        # paths: | over two lines, as a repo that lists its paths one a line writes it. The stub pipx records its argv.
        block = ("      - name: %s\n        uses: $/actions/zizmor\n        with:\n"
                 "          paths: |\n            a/\n            b/\n\n") % ZIZMOR
        rc, lines, out, argv = self.run_with_stub_pipx(block)
        self.assertIsNotNone(argv, "pipx was never called, so the action did not run zizmor\n" + out)
        self.assertEqual(argv, ["run", "zizmor==1.30.1", "a/", "b/"],
                         "with: paths: | over two lines reached pipx as its marker, not as the two paths\n" + out)
        self.assertEqual((rc, self.verdicts(lines)), (0, ["PASS"]), out)

    def test_an_unpinned_or_chained_pipx_run_is_not_a_lint_step(self):
        code, lines, out = plan_lint(self.root, workflow(step("loose", "pipx run zizmor .github/"),
                                                         step("chained", "pipx run zizmor==1.0 . && rm -rf x"),
                                                         step("pinned", "pipx run zizmor==1.0 .")))
        self.assertEqual(selected(lines), ["pinned"], out)

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
    """A cloud install copies bin/ci-job into ~/.claude/bin, with no symlink and no actions/ beside it. A remote uses with no
    claude-settings sha pin reaches code_check.py through the copy beside ci-job, else the checkout the global rules file
    names, else reads unknown. A pinned claude-settings action reads the pinned tree instead (PinnedSettings). A local uses:
    runs the repo under test's own code_check.py: from a copy it never borrows another checkout's, and in the repo under
    test with no actions/code-check it must FAIL."""

    # The branch builder and the git helper are LintTools' (one home): this class calls them, it does not copy them.
    git = LintTools.git
    lane = LintTools.lane
    # The remote form has no claude-settings pin, so it takes the copied-install route. The local forms run the repo under
    # test's own action. PLAIN is a plain run: no --lint, so no pin is read and the route is the copy's.
    CODE = step("Code check", uses="other/tools/actions/code-check@v1")
    PLAIN = ("--step", "Code check", "--base", "origin/main")
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
        rc, lines, out = self.run_job(self.CODE, args=self.PLAIN, script=ci_job, env={"CLAUDE_CONFIG_DIR": cfg})
        with open(self.log, encoding="utf-8") as f:
            log = f.read()
        self.assertRegex(log, r"(?m)^code-check: PASS$", out + log)  # code_check.py ran and passed the clean diff
        self.assertEqual((rc, self.verdicts(lines)), (0, ["PASS"]), out)

    def test_a_checkout_with_no_code_check_reads_unknown_not_fail(self):
        self.lane({"a.py": 'print("fine")\n'})
        empty = os.path.join(self.root, "empty-checkout")
        os.makedirs(empty)
        ci_job, cfg = self.install(empty)
        rc, lines, out = self.run_job(self.CODE, args=self.PLAIN, script=ci_job, env={"CLAUDE_CONFIG_DIR": cfg})
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


class ZizmorBranches(Job):
    """bin/ci-job's zizmor branch. A local $/actions/zizmor uses runs the repo under test's own run.sh, and with none
    there it FAILs, never PASS or unknown. A remote uses with no claude-settings pin finds no run.sh beside a copied install
    or in its pointer checkout, so it reads unknown and names the paths it looked at. The copied install is
    CodeCheckFromCopiedInstall's. A pinned claude-settings zizmor reads the pinned tree instead (PinnedSettings)."""

    install = CodeCheckFromCopiedInstall.install  # one home of the copied install: this class calls it, it does not copy it
    LOCAL_DOLLAR = step(ZIZMOR, uses="$/actions/zizmor", **{"with": {"paths": ".github/ actions/"}})
    REMOTE = step(ZIZMOR, uses="other/tools/actions/zizmor@v1", **{"with": {"paths": ".github/ actions/"}})
    LINT = ("--lint",)

    def pipx_env(self):
        """PATH with a stub pipx first. The zizmor branch reads a missing tool as unknown, so the stub keeps the
        missing run.sh the only reason in play."""
        bin_dir = tempfile.mkdtemp(prefix="pipx-", dir=RUN_FOLDER)
        stub = os.path.join(bin_dir, "pipx")
        with open(stub, "w", encoding="utf-8", newline="\n") as f:
            f.write("#!/bin/sh\nexit 0\n")
        os.chmod(stub, 0o755)
        return {"PATH": os.pathsep.join([bin_dir, os.environ.get("PATH", "")])}

    def test_a_local_zizmor_uses_with_no_run_sh_fails(self):
        # The fixture repo has no actions/zizmor: the local form names the repo's own run.sh, which is missing.
        rc, lines, out = self.run_job(self.LOCAL_DOLLAR, args=self.LINT, env=self.pipx_env())
        self.assertEqual((rc, self.verdicts(lines)), (1, ["FAIL"]), out)
        with open(self.log, encoding="utf-8") as f:
            log = f.read()
        self.assertIn("no run.sh at", log, out + log)  # the step's own check named the missing file

    def test_a_remote_zizmor_uses_with_no_run_sh_reads_unknown_and_names_the_paths(self):
        empty = os.path.join(self.root, "empty-checkout")
        os.makedirs(empty)
        ci_job, cfg = self.install(empty)  # no actions/ beside the copy, and the rules file names an empty checkout
        env = {**self.pipx_env(), "CLAUDE_CONFIG_DIR": cfg}
        rc, lines, out = self.run_job(self.REMOTE, args=("--step", ZIZMOR), script=ci_job, env=env)
        self.assertEqual((rc, self.verdicts(lines)), (2, ["unknown"]), out)
        self.assertIn("no run.sh: looked for", lines[0], out)


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


def load_ci_job():
    """bin/ci-job as a fresh module, so a case can call or patch its functions."""
    import importlib.machinery
    import importlib.util
    loader = importlib.machinery.SourceFileLoader("ci_job_under_test", CI_JOB)
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module


class WindowsShell(unittest.TestCase):
    """On Windows a step's bash is Git Bash by full path, never the System32 WSL launcher that PATH finds
    first (decision bare-bash-on-windows-can-resolve-to-the-wsl-stub). Built as a fake Windows tree on any host."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="winsh_", dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, self.root, True)
        self.system32 = os.path.join(self.root, "Windows", "System32")
        self.git_bin = os.path.join(self.root, "Program Files", "Git", "bin")
        for folder in (self.system32, self.git_bin):
            os.makedirs(folder)
        open(os.path.join(self.system32, "bash.exe"), "w").close()
        self.environ = {"SystemRoot": os.path.join(self.root, "Windows"), "PATH": self.system32}
        self.ci_job = load_ci_job()

    def git_bash(self):
        path = os.path.join(self.git_bin, "bash.exe")
        open(path, "w").close()
        open(os.path.join(self.git_bin, "sh.exe"), "w").close()
        return path

    def test_the_wsl_launcher_alone_is_no_shell(self):
        self.assertIsNone(self.ci_job.shell_argv(None, nt=True, environ=self.environ))

    def test_git_bash_under_program_files_runs_the_step(self):
        bash = self.git_bash()
        environ = dict(self.environ, ProgramFiles=os.path.join(self.root, "Program Files"))
        self.assertEqual(self.ci_job.shell_argv(None, nt=True, environ=environ), [bash, "-e"])
        self.assertEqual(self.ci_job.shell_argv("bash", nt=True, environ=environ)[0], bash)
        self.assertEqual(self.ci_job.shell_argv("sh", nt=True, environ=environ),
                         [os.path.join(self.git_bin, "sh.exe"), "-e"])

    def test_git_bash_on_path_after_system32_is_found(self):
        bash = self.git_bash()
        environ = dict(self.environ, PATH=self.system32 + ";" + self.git_bin)
        self.assertEqual(self.ci_job.shell_argv(None, nt=True, environ=environ)[0], bash)

    def test_a_step_with_no_git_bash_is_unknown_and_names_it(self):
        self.ci_job.shell_argv = lambda shell, nt=None, environ=None: None
        state, detail = self.ci_job.plan("      - name: lint\n        run: true\n", False, {}, self.root)[:2]
        self.assertEqual((state, detail), ("unknown", self.ci_job.no_shell("bash")))
        self.assertIn("Git Bash", self.ci_job.no_shell("bash", nt=True))

    def test_git_bash_beside_git_is_found(self):
        git_cmd = os.path.join(self.root, "Git", "cmd")
        git_bin = os.path.join(self.root, "Git", "bin")
        os.makedirs(git_cmd)
        os.makedirs(git_bin)
        for name in ("git", "git.exe"):  # which() finds `git` on POSIX and only a PATHEXT name on Windows
            with open(os.path.join(git_cmd, name), "w") as f:
                f.write("#!/bin/sh\n")
            os.chmod(os.path.join(git_cmd, name), 0o755)
        open(os.path.join(git_bin, "bash.exe"), "w").close()
        environ = dict(self.environ, PATH=git_cmd)  # one folder: the host's which() splits PATH its own way
        self.assertEqual(self.ci_job.find_git_bash(nt=True, environ=environ), os.path.join(git_bin, "bash.exe"))

    def test_the_ste_lint_body_names_its_tool_with_forward_slashes(self):
        self.ci_job.BIN = "C:\\cs\\bin"
        state, body = self.ci_job.plan(step("ste", uses="./actions/ste-lint"), True, {"base": "origin/main"},
                                       self.root)[:2]
        self.assertEqual((state, body), ("run", '"C:/cs/bin/ste-changed" "origin/main"'))

    def test_the_zizmor_body_runs_run_sh_in_the_bash_running_it(self):
        os.makedirs(os.path.join(self.root, "actions", "zizmor"))
        open(os.path.join(self.root, "actions", "zizmor", "run.sh"), "w").close()
        from unittest import mock
        with mock.patch.object(shutil, "which", lambda name, path=None: "/x/" + name):  # bash and pipx present
            state, body = self.ci_job.plan(step("zizmor", uses="./actions/zizmor"), False, {}, self.root)[:2]
        self.assertEqual(state, "run")
        self.assertIn('\n"$BASH" "%s"\n' % os.path.join(self.root, "actions", "zizmor", "run.sh").replace("\\", "/"), body)

    def test_off_windows_the_shell_is_path_bash(self):
        self.assertEqual(self.ci_job.shell_argv(None, nt=False), [shutil.which("bash"), "-e"])
        self.assertEqual(self.ci_job.shell_argv("python", nt=False), ["python3"])


PIN_USES = "shivinate7/claude-settings/actions/code-check@%s"  # a pin: any owner's claude-settings action, at a ref
READ_PINNED = 'test "$(cat "$CLAUDE_SETTINGS_DIR/marker")" = pinned'
READ_LOCAL = 'test "$(cat "$CLAUDE_SETTINGS_DIR/marker")" = local'
ABSENT_SHA = "deadbeef" * 5  # forty hex digits that neither the fixture clone nor its origin holds
CODE_CHECK_STUB = "import pathlib\npathlib.Path('pinned-code-check.txt').write_text('pinned\\n')\n"
STE_CHANGED_STUB = "#!/bin/sh\necho pinned > ste-pinned.txt\n"
# The step before a pin: a `run: |` block, then the blank line that ends it. The pin is the first line of the next step.
BUILD_LITERAL = "      - name: build\n        run: |\n          make\n\n"
BUILD_ONE_LINE = "      - name: build\n        run: make\n\n"
# A pin on a step that --lint does not run: the step prints `not run`, so the pin is read by settings_pins alone.
PIN_ONLY_USES = "shivinate7/claude-settings/actions/pin-only@%s"
# Lint scripts, each run as `python3 lint/<slug>.py <args>`. MARKER_SCRIPT writes the marker its CLAUDE_SETTINGS_DIR names
# to seen.txt and passes when that marker is argv[1]. HOLD_SCRIPT writes the tree's path to tree.txt and its marker to held.txt.
MARKER_SCRIPT = ("import os, sys\n"
                 "tree = os.environ.get('CLAUDE_SETTINGS_DIR', '')\n"
                 "marker = os.path.join(tree, 'marker')\n"
                 "seen = open(marker, encoding='utf-8').read().strip() if os.path.isfile(marker) else '(no marker)'\n"
                 "open('seen.txt', 'w', encoding='utf-8').write(seen + '\\n')\n"
                 "sys.exit(0 if seen == sys.argv[1] else 1)\n")
HOLD_SCRIPT = ("import os\n"
               "tree = os.environ.get('CLAUDE_SETTINGS_DIR', '')\n"
               "open('tree.txt', 'w', encoding='utf-8').write(tree + '\\n')\n"
               "marker = os.path.join(tree, 'marker')\n"
               "held = open(marker, encoding='utf-8').read().strip() if os.path.isfile(marker) else '(no marker)'\n"
               "open('held.txt', 'w', encoding='utf-8').write(held + '\\n')\n")
TOUCH_SCRIPT = "import sys\nopen(sys.argv[1], 'w').close()\n"  # a lint step that leaves a side file, so a run is visible


def fixture_git(cwd, *args):
    """A git command in a fixture repo, its stdout stripped. A failing fixture command raises: it is an error, not a red."""
    done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env=ENV, check=True)
    return done.stdout.strip()


def fixture_rc(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, env=ENV).returncode


def fixture_commit(cwd, files, message, executable=()):
    """Write each file (relative path -> text), commit them all, and return the new HEAD sha. A path in `executable`
    is made runnable before the add, so git records it as 755."""
    for rel, text in files.items():
        path = os.path.join(cwd, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        if rel in executable:
            os.chmod(path, 0o755)
    fixture_git(cwd, "add", "-A")
    fixture_git(cwd, "commit", "-q", "-m", message)
    return fixture_git(cwd, "rev-parse", "HEAD")


def line_of(lines, name):
    """The verdict line of the step `name`, or None."""
    for ln in lines:
        rest = ln.split(None, 1)
        if len(rest) == 2 and rest[1].startswith(name + ":"):
            return ln
    return None


class PinnedSettings(Job):
    """`--step` runs each named step in the claude-settings tree the workflow pins. The fixture: `origin` holds commit A
    (marker `pinned`), and the clone's HEAD is commit B (marker `local`). CLAUDE_SETTINGS_DIR is set by each run to a decoy
    that holds `local`, so a step that is not given the pinned tree reads what main reads. `--lint` takes the same pin for
    its lint steps; its plan reads no pin, so it lists the steps and fetches nothing."""

    def setUp(self):
        super().setUp()
        self.fixture = tempfile.mkdtemp(prefix="pinned_", dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, self.fixture, True)
        self.decoy = os.path.join(self.fixture, "decoy")
        os.makedirs(self.decoy)
        with open(os.path.join(self.decoy, "marker"), "w", encoding="utf-8", newline="\n") as f:
            f.write("local\n")

    def settings(self, *, fetch_only=False, extra=None, executable=()):
        """Build the fixture clone. Without fetch_only the clone is cloned from origin and holds A; with it the clone has
        its own history, so A is absent until ci-job fetches it. Scope first (P7): each marker reads what the case needs."""
        origin = os.path.join(self.fixture, "origin")
        self.clone = os.path.join(self.fixture, "clone")
        os.makedirs(origin)
        fixture_git(origin, "init", "-q", "-b", "main")
        self.sha_a = fixture_commit(origin, {"marker": "pinned\n", **(extra or {})}, "pinned", executable)
        if fetch_only:
            os.makedirs(self.clone)
            fixture_git(self.clone, "init", "-q", "-b", "main")
            fixture_git(self.clone, "remote", "add", "origin", origin)
        else:
            fixture_git(self.fixture, "clone", "-q", origin, self.clone)
        self.sha_b = fixture_commit(self.clone, {"marker": "local\n"}, "local")
        self.assertEqual(fixture_git(origin, "show", self.sha_a + ":marker"), "pinned")
        self.assertEqual(fixture_git(self.clone, "show", "HEAD:marker"), "local")
        absent = fixture_rc(self.clone, "cat-file", "-e", self.sha_a + "^{commit}") != 0
        self.assertEqual(absent, fetch_only, "the clone holds pin A" if fetch_only else "the clone lacks pin A")
        return self.clone

    def pinned_env(self, clone=None):
        """The env of one ci-job run: the decoy and the clone seam are the only settings values, and the run's temp
        folder is under this run's folder, so a pinned tree a run leaves is swept with the fixture."""
        tmp = os.path.join(self.fixture, "tmp")
        os.makedirs(tmp, exist_ok=True)
        env = {k: v for k, v in ENV.items() if k not in ("CLAUDE_SETTINGS_DIR", "CI_JOB_SETTINGS_CLONE", "TMPDIR")}
        env.update(CLAUDE_SETTINGS_DIR=self.decoy, CI_JOB_SETTINGS_CLONE=self.clone if clone is None else clone,
                   TMPDIR=tmp, VERDICT_LOG=self.log)
        return env

    def wf_argv(self, text, job, args=()):
        """argv of one ci-job run of `job` in the workflow `text`, written into this run's throwaway repo."""
        path = os.path.join(self.root, "wf.yml")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        return [sys.executable, CI_JOB, job, "--workflow", path, *args]

    def run_text(self, text, job, args=(), clone=None, env=None):
        done = subprocess.run(self.wf_argv(text, job, args), cwd=self.root, capture_output=True, text=True,
                              env={**self.pinned_env(clone), **(env or {})}, timeout=120)
        lines = [ln for ln in done.stdout.splitlines() if not ln.startswith("log=")]
        return done.returncode, lines, done.stdout + done.stderr

    def run_pinned(self, *steps, args=(), clone=None):
        """One ci-job run of the job: the fixture clone is the pin's source, and the decoy is the caller's own value."""
        return self.run_text(workflow(*steps), "lane", args, clone)

    def start_pinned(self, *steps, args=()):
        """Start one ci-job run in a process group of its own, output to a file. Cleanup kills the group, so a step a
        test leaves running is not kept."""
        handle = open(os.path.join(self.root, "job.out"), "wb")
        self.addCleanup(handle.close)
        proc = subprocess.Popen(self.wf_argv(workflow(*steps), "lane", args), cwd=self.root, env=self.pinned_env(),
                                stdout=handle, stderr=subprocess.STDOUT, start_new_session=True)
        self.addCleanup(self.kill_group, proc)
        return proc

    @staticmethod
    def kill_group(proc):
        try:
            os.killpg(proc.pid, signal.SIGKILL)  # the group this run started: its steps and nothing else
        except ProcessLookupError:
            pass
        proc.wait()

    @staticmethod
    def wait_for_file(path, polls=600):
        """Whether `path` appears within a bounded number of polls: a wait for a step to start, never an assert on time."""
        for _ in range(polls):
            if os.path.isfile(path):
                return True
            time.sleep(0.05)
        return False

    def worktrees(self):
        """How many worktrees the fixture clone lists, its own folder included."""
        listed = fixture_git(self.clone, "worktree", "list", "--porcelain")
        return sum(1 for ln in listed.splitlines() if ln.startswith("worktree "))

    @unittest.skipUnless(os.name == "posix", "the signal cases are posix only")
    def test_a_sigterm_mid_step_leaves_no_pinned_tree_and_no_worktree(self):
        self.settings()
        proc = self.start_pinned(
            step("pin", uses=PIN_USES % self.sha_a),
            step("slow", 'echo "$CLAUDE_SETTINGS_DIR" > seen.txt\necho started > started.txt\nsleep 30'),
            args=("--step", "slow"))
        self.assertTrue(self.wait_for_file(os.path.join(self.root, "started.txt")), "the step never started")
        seen = open(os.path.join(self.root, "seen.txt"), encoding="utf-8").read().strip()
        self.assertTrue(os.path.isdir(seen), "precondition: no pinned tree while the step runs: " + seen)
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=60)
        self.assertFalse(os.path.exists(seen), "a SIGTERM left the pinned tree on disk: " + seen)
        self.assertEqual(self.worktrees(), 1, "a SIGTERM left a worktree listed in the clone")

    @unittest.skipUnless(os.name == "posix", "the signal cases are posix only")
    def test_a_stale_pinned_tree_from_a_killed_run_is_removed_by_the_next_pinned_run(self):
        self.settings()
        proc = self.start_pinned(
            step("pin", uses=PIN_USES % self.sha_a),
            step("slow", "echo started > started.txt\nsleep 30"),
            args=("--step", "slow"))
        self.assertTrue(self.wait_for_file(os.path.join(self.root, "started.txt")), "the step never started")
        proc.kill()  # SIGKILL: no handler runs, so the run leaves its worktree behind
        proc.wait(timeout=60)
        self.assertEqual(self.worktrees(), 2, "precondition: the killed run left its worktree listed")
        rc, lines, out = self.run_pinned(step("pin", uses=PIN_USES % self.sha_a), step("quick", READ_PINNED),
                                         args=("--step", "quick"))
        self.assertEqual(by_step(lines).get("quick"), "PASS", "the next pinned run did not read its pin:\n" + out)
        self.assertEqual(self.worktrees(), 1, "the next pinned run left the killed run's worktree listed:\n" + out)

    def test_a_missing_settings_clone_is_unknown_with_exit_two_not_a_crash(self):
        self.settings()
        missing = os.path.join(self.fixture, "no-such-clone")
        rc, lines, out = self.run_pinned(step("pin", uses=PIN_USES % self.sha_a), step("read pinned marker", READ_PINNED),
                                         args=("--step", "read pinned marker"), clone=missing)
        self.assertEqual((rc, by_step(lines).get("read pinned marker")), (2, "unknown"),
                         "a missing CI_JOB_SETTINGS_CLONE must be one unknown line, exit 2:\n" + out)
        self.assertNotIn("Traceback", out, "a missing CI_JOB_SETTINGS_CLONE crashed ci-job:\n" + out)

    def test_plan_with_an_unfetchable_pin_plans_unknown_and_makes_no_worktree(self):
        self.settings()
        rc, lines, out = self.run_pinned(step("pin", uses=PIN_USES % ABSENT_SHA), step("write", "echo ran > ran.txt"),
                                         args=("--step", "write", "--plan"))
        self.assertEqual((rc, by_step(lines).get("write")), (2, "unknown"),
                         "--plan must plan an unfetchable pin as unknown, not 'would run':\n" + out)
        self.assertEqual(self.worktrees(), 1, "--plan made a worktree:\n" + out)

    def test_a_step_uses_the_pin_of_its_own_job(self):
        self.settings()
        text = ("name: t\non: push\njobs:\n  checks:\n    runs-on: ubuntu-latest\n    steps:\n"
                + step("pin", uses=PIN_USES % self.sha_a) + step("read pinned marker", READ_PINNED)
                + "  other:\n    runs-on: ubuntu-latest\n    steps:\n" + step("pin b", uses=PIN_USES % self.sha_b))
        rc, lines, out = self.run_text(text, "checks", args=("--step", "read pinned marker"))
        self.assertEqual(by_step(lines).get("read pinned marker"), "PASS",
                         "a step of `checks` must read job checks' pin (A), not unknown for the other job's B:\n" + out)

    def test_a_step_reads_the_pinned_tree_and_its_twin_reads_the_local_one(self):
        self.settings()
        rc, lines, out = self.run_pinned(
            step("pin", uses=PIN_USES % self.sha_a),
            step("read pinned marker", READ_PINNED),
            step("read local marker", READ_LOCAL),
            args=("--step", "read pinned marker", "--step", "read local marker"))
        self.assertEqual(by_step(lines).get("read pinned marker"), "PASS",
                         "the pinned step failed: it did not read the pinned tree\n" + out)
        self.assertEqual(by_step(lines).get("read local marker"), "FAIL",
                         "the local twin passed: the step read the local tree, not the pinned one\n" + out)

    def test_one_real_pin_past_repeats_comments_and_run_text_still_pins_the_tree(self):
        self.settings()
        rc, lines, out = self.run_pinned(
            step("pin", uses=PIN_USES % self.sha_a + " # v1"),
            step("repeat", uses=PIN_USES % self.sha_a),
            "      # - uses: shivinate7/claude-settings/actions/zizmor@%s\n" % self.sha_b,
            step("notes", 'echo "# uses: shivinate7/claude-settings/actions/code-check@%s"\necho "don\'t stop"' % self.sha_b),
            step("read pinned marker", READ_PINNED),
            args=("--step", "read pinned marker"))
        self.assertNotEqual(by_step(lines).get("read pinned marker"), "unknown",
                            "the pin scan counted more than one pin: " + str(line_of(lines, "read pinned marker")))
        self.assertEqual(by_step(lines).get("read pinned marker"), "PASS",
                         "the step did not read the pinned tree (one pin, comments and run text ignored):\n" + out)

    def test_two_distinct_pins_make_every_named_step_unknown_and_run_none(self):
        self.settings()
        rc, lines, out = self.run_pinned(
            step("pin a", uses=PIN_USES % self.sha_a),
            step("pin b", uses=PIN_USES % self.sha_b),
            step("one", "echo one > one.txt"),
            step("two", "echo two > two.txt"),
            args=("--step", "one", "--step", "two"))
        self.assertEqual((rc, by_step(lines).get("one"), by_step(lines).get("two")), (2, "unknown", "unknown"),
                         "two distinct pins must make each named step unknown, exit 2:\n" + out)
        self.assertIn("pin", (line_of(lines, "one") or "").lower(), "the unknown line must name the pins: " + out)
        for name in ("one.txt", "two.txt"):
            self.assertFalse(os.path.exists(os.path.join(self.root, name)), "a step ran under two pins: " + name)

    def test_a_pin_ref_that_is_not_a_sha_is_unknown(self):
        self.settings()
        rc, lines, out = self.run_pinned(
            step("pin", uses=PIN_USES % "main"),
            step("write", "echo ran > ran.txt"),
            args=("--step", "write"))
        self.assertEqual((rc, by_step(lines).get("write")), (2, "unknown"),
                         "a pin on @main must make the named step unknown, exit 2:\n" + out)
        line = line_of(lines, "write") or ""
        self.assertTrue("main" in line or "sha" in line.lower(), "the unknown line must name the ref: " + line)
        self.assertFalse(os.path.exists(os.path.join(self.root, "ran.txt")), "a step ran under a ref pin")

    def test_a_pin_sha_that_neither_clone_nor_origin_has_is_unknown(self):
        self.settings()
        rc, lines, out = self.run_pinned(
            step("pin", uses=PIN_USES % ABSENT_SHA),
            step("write", "echo ran > ran.txt"),
            args=("--step", "write"))
        self.assertEqual((rc, by_step(lines).get("write")), (2, "unknown"),
                         "a pin that cannot be fetched must make the named step unknown, exit 2:\n" + out)
        line = line_of(lines, "write") or ""
        self.assertTrue("fetch" in line.lower() or ABSENT_SHA in line, "the unknown line must name the fetch: " + line)
        self.assertFalse(os.path.exists(os.path.join(self.root, "ran.txt")), "a step ran under an unfetchable pin")

    def test_no_pin_leaves_the_settings_dir_as_the_caller_set_it(self):  # P2 green control: main passes this too
        self.settings()
        rc, lines, out = self.run_pinned(
            step("plain", 'test "$CLAUDE_SETTINGS_DIR" = "%s"' % self.decoy),
            args=("--step", "plain"))
        self.assertEqual((rc, by_step(lines).get("plain")), (0, "PASS"),
                         "with no pin, ci-job must not change CLAUDE_SETTINGS_DIR:\n" + out)

    def test_a_plain_run_with_a_pin_leaves_the_settings_dir_alone(self):  # control: --step alone pins, not a plain run
        self.settings()
        rc, lines, out = self.run_pinned(
            step("pin", uses=PIN_USES % self.sha_a),
            step("plain", 'test "$CLAUDE_SETTINGS_DIR" = "%s"' % self.decoy))
        self.assertEqual(by_step(lines).get("plain"), "PASS",
                         "a plain run must not set CLAUDE_SETTINGS_DIR to the pinned tree:\n" + out)

    def test_the_pinned_tree_is_gone_after_the_run(self):
        self.settings()
        rc, lines, out = self.run_pinned(
            step("pin", uses=PIN_USES % self.sha_a),
            step("record", 'echo "$CLAUDE_SETTINGS_DIR" > seen.txt\ncp "$CLAUDE_SETTINGS_DIR/marker" held.txt'),
            args=("--step", "record"))
        seen_file = os.path.join(self.root, "seen.txt")
        seen = open(seen_file, encoding="utf-8").read().strip() if os.path.isfile(seen_file) else ""
        held_file = os.path.join(self.root, "held.txt")  # the marker, copied out during the run: the tree is gone after it
        held = open(held_file, encoding="utf-8").read().strip() if os.path.isfile(held_file) else None
        self.assertEqual(held, "pinned", "the step did not run in a pinned tree (its marker copy held %r):\n%s"
                         % (held, out))
        self.assertFalse(os.path.exists(seen), "the pinned tree is still on disk after the run: " + seen)
        listed = fixture_git(self.clone, "worktree", "list", "--porcelain")
        self.assertEqual(sum(1 for ln in listed.splitlines() if ln.startswith("worktree ")), 1,
                         "the clone still lists a worktree after the run:\n" + listed)

    def test_a_step_env_settings_dir_wins_over_the_pin(self):
        self.settings()
        rc, lines, out = self.run_pinned(
            step("pin", uses=PIN_USES % self.sha_a),
            step("own env", 'test "$CLAUDE_SETTINGS_DIR" = own-env-x', env={"CLAUDE_SETTINGS_DIR": "own-env-x"}),
            step("no env", READ_PINNED),
            args=("--step", "own env", "--step", "no env"))
        self.assertEqual(by_step(lines).get("own env"), "PASS",
                         "a step's own env: CLAUDE_SETTINGS_DIR was replaced:\n" + out)
        self.assertEqual(by_step(lines).get("no env"), "PASS",
                         "a step without env: did not read the pinned tree:\n" + out)

    def test_a_remote_code_check_runs_from_the_pinned_tree_only(self):
        self.settings(extra={"actions/code-check/code_check.py": CODE_CHECK_STUB})
        rc, lines, out = self.run_pinned(
            step("code check", uses=PIN_USES % self.sha_a),
            args=("--base", "origin/main", "--step", "code check"))
        line = line_of(lines, "code check") or ""
        self.assertTrue(os.path.isfile(os.path.join(self.root, "pinned-code-check.txt")),
                        "the pinned code_check.py did not run: " + line + "\n" + out)
        found = re.search(r"\(code_check\.py: (.+)\)$", line)
        self.assertTrue(found, "the verdict line does not name the code_check.py it ran: " + line)
        local = os.path.join(CHECKOUT, "actions", "code-check", "code_check.py")
        self.assertNotEqual(os.path.realpath(found.group(1)), os.path.realpath(local),
                            "code_check.py ran from the local copy, not the pinned tree: " + line)

    def test_a_remote_ste_lint_runs_the_pinned_trees_ste_changed(self):
        self.settings(extra={"bin/ste-changed": STE_CHANGED_STUB}, executable=("bin/ste-changed",))
        rc, lines, out = self.run_pinned(
            step("ste lint", uses="shivinate7/claude-settings/actions/ste-lint@%s" % self.sha_a),
            args=("--base", "origin/main", "--step", "ste lint"))
        self.assertTrue(os.path.isfile(os.path.join(self.root, "ste-pinned.txt")),
                        "the remote ste-lint ran ci-job's own bin/ste-changed, not the pinned tree's:\n" + out)

    def test_a_pin_missing_from_the_clone_is_fetched_from_its_origin(self):
        self.settings(fetch_only=True)
        rc, lines, out = self.run_pinned(
            step("pin", uses=PIN_USES % self.sha_a),
            step("read pinned marker", READ_PINNED),
            args=("--step", "read pinned marker"))
        self.assertNotEqual(by_step(lines).get("read pinned marker"), "unknown",
                            "the pin was not fetched from its origin: " + str(line_of(lines, "read pinned marker")))
        self.assertEqual(by_step(lines).get("read pinned marker"), "PASS",
                         "the step did not read the fetched pin's tree:\n" + out)

    def dash_pin_after(self, build):
        """A workflow whose step before the pin is `build`. The pin is the first line of its own step (`- uses:`)."""
        return workflow(build, "      - uses: %s\n\n" % (PIN_USES % self.sha_a), step("read pinned marker", READ_PINNED))

    def test_a_pin_on_the_first_line_after_a_run_block_is_read(self):
        self.settings()
        text = self.dash_pin_after(BUILD_LITERAL)
        self.assertIn(BUILD_LITERAL + "      - uses: " + PIN_USES % self.sha_a, text,
                      "precondition: the fixture's pin is not the first line of the step after a `run: |` block")
        rc, lines, out = self.run_text(text, "lane", args=("--step", "read pinned marker"))
        self.assertEqual(by_step(lines).get("read pinned marker"), "PASS",
                         "the named step did not read the pinned tree: its pin after a `run: |` block was skipped:\n" + out)

    def test_a_pin_on_the_first_line_after_a_one_line_run_is_read(self):  # P2 green control: the old code reads this pin
        self.settings()
        text = self.dash_pin_after(BUILD_ONE_LINE)
        self.assertIn(BUILD_ONE_LINE + "      - uses: " + PIN_USES % self.sha_a, text,
                      "precondition: the fixture's pin is not the first line of the step after a one-line run")
        rc, lines, out = self.run_text(text, "lane", args=("--step", "read pinned marker"))
        self.assertEqual(by_step(lines).get("read pinned marker"), "PASS",
                         "the named step did not read the pinned tree after a one-line run:\n" + out)

    def lint_step(self, name, slug, script, *argv):
        """A lint step, `python3 lint/<slug>.py <argv>`, with its script written into this run's throwaway repo. --lint picks
        a step by the shape of its command, so a lint step is a script under lint/, never a shell line."""
        path = os.path.join(self.root, "lint", slug + ".py")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(script)
        return step(name, " ".join(["python3", "lint/%s.py" % slug, *argv]))

    def root_file(self, rel):
        """The text a lint step wrote to `rel` in this run's folder, or "" when it wrote none."""
        path = os.path.join(self.root, rel)
        return open(path, encoding="utf-8").read().strip() if os.path.isfile(path) else ""

    # --lint runs its lint steps in the pinned tree, as --step does. The two marked control hold what must not change.

    def test_lint_runs_a_lint_step_in_the_pinned_tree(self):
        self.settings()
        rc, lines, out = self.run_pinned(
            step("pin", uses=PIN_ONLY_USES % self.sha_a),
            self.lint_step("read pinned", "read_marker", MARKER_SCRIPT, "pinned"),
            args=("--lint",))
        self.assertEqual(by_step(lines).get("read pinned"), "PASS",
                         "the lint step read the marker %r, not the pinned tree's:\n%s" % (self.root_file("seen.txt"), out))

    def test_lint_runs_a_remote_ste_lint_from_the_pinned_tree_only(self):
        self.settings(extra={"bin/ste-changed": STE_CHANGED_STUB}, executable=("bin/ste-changed",))
        rc, lines, out = self.run_pinned(
            step("ste lint", uses="shivinate7/claude-settings/actions/ste-lint@%s" % self.sha_a),
            args=("--lint", "--base", "origin/main"))
        self.assertTrue(os.path.isfile(os.path.join(self.root, "ste-pinned.txt")),
                        "--lint did not run the pinned tree's bin/ste-changed:\n" + out)

    def test_lint_runs_a_remote_code_check_from_the_pinned_tree_only(self):
        self.settings(extra={"actions/code-check/code_check.py": CODE_CHECK_STUB})
        rc, lines, out = self.run_pinned(
            step("code check", uses=PIN_USES % self.sha_a),
            args=("--lint", "--base", "origin/main"))
        self.assertTrue(os.path.isfile(os.path.join(self.root, "pinned-code-check.txt")),
                        "--lint did not run the pinned tree's code_check.py:\n" + out)

    def test_lint_with_two_distinct_pins_makes_each_lint_step_unknown_and_runs_none(self):
        self.settings()
        rc, lines, out = self.run_pinned(
            step("pin a", uses=PIN_ONLY_USES % self.sha_a),
            step("pin b", uses=PIN_ONLY_USES % self.sha_b),
            self.lint_step("one", "touch", TOUCH_SCRIPT, "one.txt"),
            self.lint_step("two", "touch", TOUCH_SCRIPT, "two.txt"),
            args=("--lint",))
        self.assertEqual(sorted(n for n in by_step(lines) if n in ("one", "two")), ["one", "two"],
                         "precondition: --lint did not list both lint steps:\n" + out)
        self.assertEqual((rc, by_step(lines)["one"], by_step(lines)["two"]), (2, "unknown", "unknown"),
                         "two distinct pins must make each lint step unknown, exit 2:\n" + out)
        for name in ("one", "two"):
            self.assertIn("pin", (line_of(lines, name) or "").lower(),
                          "the unknown line must name the pins: " + str(line_of(lines, name)))
        for side in ("one.txt", "two.txt"):
            self.assertFalse(os.path.exists(os.path.join(self.root, side)), "a lint step ran under two pins: " + side)

    def test_lint_with_a_pin_that_is_no_sha_makes_each_lint_step_unknown_and_runs_none(self):
        self.settings()
        rc, lines, out = self.run_pinned(
            step("pin", uses=PIN_ONLY_USES % "main"),
            self.lint_step("one", "touch", TOUCH_SCRIPT, "one.txt"),
            self.lint_step("two", "touch", TOUCH_SCRIPT, "two.txt"),
            args=("--lint",))
        self.assertEqual(sorted(n for n in by_step(lines) if n in ("one", "two")), ["one", "two"],
                         "precondition: --lint did not list both lint steps:\n" + out)
        self.assertEqual((rc, by_step(lines)["one"], by_step(lines)["two"]), (2, "unknown", "unknown"),
                         "a pin on @main must make each lint step unknown, exit 2:\n" + out)
        for name in ("one", "two"):
            self.assertIn("main", line_of(lines, name) or "",
                          "the unknown line must name the ref: " + str(line_of(lines, name)))
        for side in ("one.txt", "two.txt"):
            self.assertFalse(os.path.exists(os.path.join(self.root, side)), "a lint step ran under a ref pin: " + side)

    def test_lint_removes_the_pinned_tree_after_the_run(self):
        self.settings()
        rc, lines, out = self.run_pinned(
            step("pin", uses=PIN_ONLY_USES % self.sha_a),
            self.lint_step("record", "hold", HOLD_SCRIPT),
            args=("--lint",))
        held = self.root_file("held.txt")  # scope first: the step ran in the pinned tree, so the tree had to exist
        self.assertEqual(held, "pinned", "precondition: the lint step did not read the pinned tree (its marker %r):\n%s" % (held, out))
        tree = self.root_file("tree.txt")
        self.assertFalse(os.path.exists(tree), "the pinned tree is still on disk after --lint: " + tree)
        self.assertEqual(self.worktrees(), 1, "--lint left a worktree listed in the clone:\n" + out)

    def test_lint_with_no_pin_leaves_the_settings_dir_as_the_caller_set_it(self):  # control: passes on the old code too
        self.settings()
        rc, lines, out = self.run_pinned(
            self.lint_step("read decoy", "read_marker", MARKER_SCRIPT, "local"),
            args=("--lint",))
        self.assertEqual((rc, by_step(lines).get("read decoy")), (0, "PASS"),
                         "with no pin, --lint must not change CLAUDE_SETTINGS_DIR:\n" + out)

    def test_lint_plan_with_a_pin_lists_would_run_and_fetches_nothing(self):  # control: passes on the old code too
        self.settings(fetch_only=True)  # the clone lacks the pin: a plan that needed it would fail here
        rc, lines, out = self.run_text(
            workflow(step("pin", uses=PIN_ONLY_USES % self.sha_a),
                     self.lint_step("read pinned", "read_marker", MARKER_SCRIPT, "pinned")),
            "lane", args=("--lint", "--plan", "--base", "origin/main"))
        self.assertEqual((rc, selected(lines)), (0, ["read pinned"]),
                         "--lint --plan must list its lint steps as `would run` when the clone lacks the pin:\n" + out)
        self.assertNotEqual(fixture_rc(self.clone, "cat-file", "-e", self.sha_a + "^{commit}"), 0,
                            "--lint --plan fetched the pin:\n" + out)
        self.assertEqual(self.worktrees(), 1, "--lint --plan made a worktree:\n" + out)

    # The remote claude-settings actions of a pinned job read the pinned tree only. The copy beside ci-job and the rules
    # file's checkout are the route for a remote uses with no pin: CodeCheckFromCopiedInstall and ZizmorBranches keep it.
    git = LintTools.git
    lane = LintTools.lane

    def test_a_remote_code_check_with_no_code_check_in_the_pinned_tree_reads_unknown_naming_the_path(self):
        self.settings()  # the pinned tree has no actions/code-check
        rc, lines, out = self.run_pinned(
            step("code check", uses=PIN_USES % self.sha_a),
            args=("--lint", "--base", "origin/main"))
        self.assertEqual((rc, by_step(lines).get("code check")), (2, "unknown"), out)
        line = line_of(lines, "code check") or ""
        self.assertIn(os.path.join("actions", "code-check", "code_check.py"), line,
                      "the unknown line must name the code_check.py it looked for: " + line)
        self.assertIn(self.fixture, line, "the unknown line must name the pinned tree, not the local checkout: " + line)

    def test_a_remote_code_check_under_lint_runs_the_pinned_trees_code_check_py_for_real(self):
        if not pipx_runs_pinned_ruff():
            self.skipTest("pipx cannot run code_check's pinned ruff here: no pipx, or offline with no cached copy")
        code = {rel: open(os.path.join(CHECKOUT, rel), encoding="utf-8").read()
                for rel in ("actions/code-check/code_check.py", "actions/code-check/standard.json")}
        self.settings(extra=code)  # code_check reads standard.json beside itself, so the pinned tree needs both
        self.lane({"a.py": 'print("fine")\n'})
        rc, lines, out = self.run_pinned(
            step("code check", uses=PIN_USES % self.sha_a),
            args=("--lint", "--base", "origin/main"))
        with open(self.log, encoding="utf-8") as f:
            log = f.read()
        self.assertEqual((rc, by_step(lines).get("code check")), (0, "PASS"), out + log)
        self.assertRegex(log, r"(?m)^code-check: PASS$", out + log)  # code_check.py ran from the pinned tree on a clean diff

    def test_a_remote_zizmor_with_no_run_sh_in_the_pinned_tree_reads_unknown_naming_the_path(self):
        self.settings()  # the pinned tree has no actions/zizmor/run.sh
        rc, lines, out = self.run_text(
            workflow(step(ZIZMOR, uses="shivinate7/claude-settings/actions/zizmor@%s" % self.sha_a,
                          **{"with": {"paths": ".github/ actions/"}})),
            "lane", args=("--lint",), env=ZizmorBranches.pipx_env(self))  # the stub pipx: the missing run.sh is the only reason
        self.assertEqual((rc, by_step(lines).get(ZIZMOR)), (2, "unknown"), out)
        line = line_of(lines, ZIZMOR) or ""
        self.assertIn(os.path.join("actions", "zizmor", "run.sh"), line,
                      "the unknown line must name the run.sh it looked for: " + line)
        self.assertIn(self.fixture, line, "the unknown line must name the pinned tree, not the local checkout: " + line)


if __name__ == "__main__":
    try:
        unittest.main()
    finally:
        shutil.rmtree(RUN_FOLDER, ignore_errors=True)
