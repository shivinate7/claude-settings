#!/usr/bin/env python3
"""Fixture suite for bin/ci-job: each case writes a workflow into a throwaway repo and runs one job.

Red cases: a multi-line step whose last line fails, a missing tool (named, behind xargs, or exit 127),
a `uses:` step, an `if:` or env expression the runner cannot read, and a pull-request step with no base.
None of them may read PASS. The GithubBaseRef class: the GITHUB_BASE_REF each step gets from --base, unset with none.
The last class plans the real checks job: every step gets one line.
The last two classes: the code-check step from a copied install, and a step quiet past the stall limit.
PinnedHarness: a remote claude-settings uses: pinned to a sha runs its harness from a tree at that sha, never the local copy (R67: no flag).
StepMaps reads a step's with: and env: values: a block scalar as its lines, an inline comment dropped.
StepSelect: --step runs only the named steps; a name no step has is one unknown line, exit 2.
PinnedSettings: --step runs each remote action step in a worktree of the claude-settings commit it pins (one per distinct
40-hex sha on its `<owner>/claude-settings/actions/<name>@<ref>` uses: line); a ref that is no sha or an unfetchable sha is unknown
for the steps that need it, and a plain step under two pins is unknown.
A blocked named step stops only itself; under two pins CLAUDE_SETTINGS_DIR is the caller's; one pin builds one tree.
SettingsPins: settings_pins reads a `#` inside quotes, and a lone quote, as text; a run: block is script, never a pin.
SuiteSteps: --lint runs a CI step that runs a hooks/merge/lint suite only when the selector picks it for the diff; a selector
  that cannot run exits 2.
  SuiteSteps also covers a multi-line step with a preamble line, a suite with an argument, a suite that reaches a changed
  module through an import, a selector that hangs, a picked suite whose step is in another job, and a guard preamble
  (`[ -d node_modules/x ] || npm ci`, or an if block) before a picked suite. It also covers a preamble line that ends in
  `&&`, `||` or `|`, which the marker must not join, and a failed preamble that does not block a lint step after it.
Lint mode: a --lint run that picks no lint step is unknown, exit 2; a lint step that a pull-request run would run reads
unknown when it is skipped; a lint step that runs only off a pull request reads skipped, and the run still exits 0.
ParallelLint: --lint runs its lint steps at once (CI_JOB_LINT_WORKERS, else the cpu count up to 4), keeps the printed
lines and each step's log lines in workflow order, and treats an install step as a barrier. Overlap is proven by rendezvous.
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
from workflow_steps import run_body, settings_pins, step_blocks, step_env, step_with  # noqa: E402  the one home of the step parser
import workflow_steps  # noqa: E402  the module itself, for the scalar reader it holds (yaml_scalar)
sys.path.append(os.path.join(HERE, "..", "hooks"))  # append: the pin note's names (hooks/pin_note.py)
from pin_note import ENV as PIN_NOTE_ENV  # noqa: E402  the one home of the pin note's variable (hooks/pin_note.py)
RUN_FOLDER = _test_temp.run_folder()
CHECKOUT = os.path.abspath(os.path.join(HERE, ".."))
CI_JOB = os.path.join(HERE, "..", "bin", "ci-job")
CHECKS = os.path.join(HERE, "..", ".github", "workflows", "checks.yml")
WORKFLOWS = os.path.join(HERE, "..", ".github", "workflows")
STALL_WATCH = os.path.join(HERE, "..", "hooks", "stall_watch.py")
ENV = _test_git.apply(dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull, GIT_AUTHOR_NAME="t",
                           GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t"))
ENV.pop("VERDICT_LOG", None)
ENV.pop("CI_JOB_LINT_WORKERS", None)


def workflow(*steps, job="lane", other=None):
    """The workflow of one run: `job` runs `steps`, and a second job named `other` runs the `other` steps (by default one
    step that exits 1)."""
    other_steps = "".join(other) if other is not None else "      - run: exit 1\n"
    return ("name: t\non: push\njobs:\n  %s:\n    runs-on: ubuntu-latest\n    steps:\n" % job) + "".join(steps) + \
        "\n  other:\n    runs-on: ubuntu-latest\n    steps:\n" + other_steps


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
    NPM_OK = 'touch installed.marker\necho "$*" >> npm-calls.txt'  # an npm stub that succeeds and records its arguments

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="cijob_", dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, self.root, True)
        subprocess.run(["git", "init", "-q", "-b", "main", self.root], check=True, env=ENV)
        self.log = os.path.join(self.root, "verdict.log")

    def job_call(self, *steps, args=(), env=None, script=CI_JOB, launch=(), job="lane", other=None):
        """argv and env of one run of the job: its workflow is written into the throwaway repo. launch: python's own flags
        before the script, such as `-c` with a launcher's code. job: the job the steps belong to; other: the steps of a second
        job named `other` (by default one step that exits 1)."""
        path = os.path.join(self.root, "wf.yml")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(workflow(*steps, job=job, other=other))
        env = {**ENV, "VERDICT_LOG": self.log, **{k: v for k, v in os.environ.items() if k == "VERDICT_HEARTBEAT"},
               **(env or {})}
        return [sys.executable, *launch, script, job, "--workflow", path, *args], env

    def run_job(self, *steps, args=(), env=None, script=CI_JOB, launch=(), job="lane", other=None, stdin=None):
        argv, env = self.job_call(*steps, args=args, env=env, script=script, launch=launch, job=job, other=other)
        done = subprocess.run(argv, cwd=self.root, capture_output=True, text=True, env=env, timeout=120, stdin=stdin)
        lines = [ln for ln in done.stdout.splitlines() if not ln.startswith("log=")]
        return done.returncode, lines, done.stdout + done.stderr

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

    def path_without(self, tool):
        """This process's PATH with each folder that holds `tool` left out, so a step cannot find that tool."""
        return {"PATH": os.pathsep.join(d for d in os.environ.get("PATH", "").split(os.pathsep)
                                        if d and not os.path.exists(os.path.join(d, tool)))}

    def verdicts(self, lines):
        return [ln.split()[0] if not ln.startswith("not run locally") else "not run locally" for ln in lines
                if not NOT_RUN.match(ln) and not SUMMARY.match(ln)]  # a --lint run's not-run and summary lines are no verdict

    def seen_after(self, *steps, args=(), env=None):
        """(verdicts, the value the step wrote or a note that it wrote none, output) of one run of the job. ci-job relays
        no step output, so a step writes the value it sees to seen.txt."""
        path = os.path.join(self.root, "seen.txt")
        if os.path.exists(path):
            os.remove(path)
        rc, lines, out = self.run_job(*steps, args=args, env=env)
        if not os.path.exists(path):
            return self.verdicts(lines), "(no seen.txt: the step did not run)", out
        with open(path, encoding="utf-8") as f:
            return self.verdicts(lines), f.read(), out


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
        for rel in ("lint/check_comment_narration.py", "lint/layout.py", "lint/layout.json", "lint/diff_moves.py",
                    "hooks/_nowindow.py", "lint/code_check_standard.json"):
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

    def test_a_pull_request_lint_step_with_no_base_and_no_origin_main_reads_unknown_not_skipped(self):
        self.lane_adds_narration(origin=False)
        _, lines, out = plan_lint(self.root, workflow(self.NARRATION), extra=("--base", "origin/main"))
        self.assertEqual(selected(lines), ["Comment narration check"], out)  # the scope: a pull-request run would run this lint step
        rc, lines, out = self.run_job(self.NARRATION, args=("--lint",))
        self.assertEqual(by_step(lines).get("Comment narration check"), "unknown", out)  # the exit code is no proof: the no-base line gives 2 too
        self.assertEqual(rc, 2, out)


class GithubBaseRef(Job):
    """A pull-request run sets GITHUB_BASE_REF in each step's env, as the Actions runner does: the base without its
    remote. With no base there is no pull-request run, so the variable is unset even when the caller's env sets it.
    ci-job relays no step output, so each step writes the value it sees to seen.txt. `<unset>` is no ref name."""

    SEEN = "printf '%s' \"${GITHUB_BASE_REF-<unset>}\" > seen.txt"

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


class PinNoteEnv(Job):
    """ci-job sets the pin note's variable on its ste-lint step only (decision action-pins-follow-sessions). A caller that
    exports it must not reach any other step: ci-job strips it from each step's env. The step writes what it sees to seen.txt."""

    SEEN = "printf '%s' \"${" + PIN_NOTE_ENV + "-<unset>}\" > seen.txt"

    def test_a_caller_export_of_the_pin_note_variable_never_reaches_another_step(self):
        verdicts, seen, out = self.seen_after(step("seen", self.SEEN), env={PIN_NOTE_ENV: "1"})
        self.assertEqual(verdicts, ["PASS"], out)
        self.assertEqual(seen, "<unset>", "a step that is not ste-lint saw the pin note variable: " + out)


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


class SettingsPins(unittest.TestCase):
    """settings_pins, the one pin reader (lint/workflow_steps.py), read as text. A `#` inside quotes is text, so the pin
    after it is read. A lone quote in text opens no quote. A `#` after a space and outside quotes starts a comment. A
    run: block is script, never a pin, whatever its quotes, comment openers or header comment."""

    HEAD = "name: t\non: push\njobs:\n  lane:\n    runs-on: ubuntu-latest\n    steps:\n"  # the step after it is line 7
    SHA = "a" * 40
    USES = "o/claude-settings/actions/ste-lint@" + "a" * 40

    def test_a_hash_inside_double_quotes_is_text_and_the_pin_after_it_is_read(self):
        found = settings_pins(self.HEAD + '      - {name: "Lint #2", uses: %s}\n' % self.USES)
        self.assertEqual(found, [("ste-lint", self.SHA, 7)], "a # inside double quotes hid the pin after it")

    def test_a_hash_inside_single_quotes_is_text_and_the_pin_after_it_is_read(self):
        found = settings_pins(self.HEAD + "      - {name: 'a # b', uses: %s}\n" % self.USES)
        self.assertEqual(found, [("ste-lint", self.SHA, 7)], "a # inside single quotes hid the pin after it")

    def test_a_lone_quote_in_text_opens_no_quote_and_a_comment_after_the_pin_is_dropped(self):  # P2 green control
        found = settings_pins(self.HEAD + "      - {name: don't, uses: %s}  # it's the lint step\n" % self.USES)
        self.assertEqual(found, [("ste-lint", self.SHA, 7)], "a lone quote in text hid the pin")

    def test_a_multi_line_run_block_is_script_and_its_quotes_and_comment_openers_hide_nothing(self):  # P2 green control
        body = ('      - name: notes\n        run: |\n          echo "# uses: o/claude-settings/actions/code-check@%s"\n'
                "          echo don't \"stop\n"
                "      - {name: lint, uses: %s}\n") % ("b" * 40, self.USES)
        found = settings_pins(self.HEAD + body)
        self.assertEqual(found, [("ste-lint", self.SHA, 11)],
                         "a run: block's text was read as a pin, or the pin after the block was lost")

    def test_a_run_block_with_a_comment_after_its_literal_header_is_script_and_no_pin(self):
        step = "      - run: | # note\n          echo %s\n" % self.USES
        self.assertEqual(run_body(step), "echo %s\n" % self.USES,
                         "precondition: run_body did not read run: | # note as a block")
        self.assertEqual(settings_pins(self.HEAD + step), [],
                         "run: | # note: the header comment hid the block, so its script line was read as a pin")

    def test_a_run_block_with_a_comment_after_its_folded_header_is_script_and_no_pin(self):
        step = "      - run: > # note\n          echo %s\n" % self.USES
        self.assertEqual(run_body(step), "echo %s\n" % self.USES,
                         "precondition: run_body did not read run: > # note as a block")
        self.assertEqual(settings_pins(self.HEAD + step), [],
                         "run: > # note: the header comment hid the block, so its script line was read as a pin")

    def test_a_plain_literal_run_block_with_the_same_script_line_is_no_pin(self):  # P2 green control
        step = "      - run: |\n          echo %s\n" % self.USES
        self.assertEqual(settings_pins(self.HEAD + step), [], "a run: | block's script line was read as a pin")


class ScalarOneHome(unittest.TestCase):
    """workflow_steps.yaml_scalar is the one reader of a YAML scalar: outer quotes off, a trailing comment cut, and a `#`
    inside quotes kept. bin/ci-job's uses() reads its value with the same rule, and the split guard reads its scalars
    with it too."""

    def scalar(self, raw):
        self.assertTrue(hasattr(workflow_steps, "yaml_scalar"),
                        "lint/workflow_steps.py has no yaml_scalar: no one home for the scalar reader")
        return workflow_steps.yaml_scalar(raw)

    def test_a_plain_value_is_itself(self):
        self.assertEqual(self.scalar("x"), "x")

    def test_a_double_quoted_value_loses_its_quotes(self):
        self.assertEqual(self.scalar('"x"'), "x")

    def test_a_single_quoted_value_loses_its_quotes(self):
        self.assertEqual(self.scalar("'x'"), "x")

    def test_a_quoted_value_with_a_trailing_comment_is_the_value(self):
        self.assertEqual(self.scalar('"x" # c'), "x")

    def test_a_hash_inside_quotes_is_text(self):
        self.assertEqual(self.scalar("'a # b'"), "a # b")

    def test_a_plain_value_with_a_trailing_comment_is_the_value(self):
        self.assertEqual(self.scalar("x # c"), "x")

    def test_an_empty_quoted_value_is_empty(self):
        self.assertEqual(self.scalar("''"), "")

    def test_a_single_quote_escape_is_one_quote(self):
        self.assertEqual(self.scalar("'it''s'"), "it's")

    def test_a_double_quote_escape_is_one_quote(self):
        self.assertEqual(self.scalar('"a\\"b"'), 'a"b')

    def test_a_hash_with_no_space_before_it_is_text(self):  # control: a comment needs a space before its #
        self.assertEqual(self.scalar("x#y"), "x#y")

    def test_ci_job_uses_reads_a_hash_inside_quotes_as_yaml_does(self):
        ci_job = load_ci_job()
        self.assertEqual(ci_job.uses(step("uses step", uses="'a # b'")), "a # b")

    def test_ci_job_uses_reads_a_quoted_value_with_a_trailing_comment(self):  # control: the comment is cut, the quotes go
        ci_job = load_ci_job()
        self.assertEqual(ci_job.uses(step("uses step", uses='"x" # c')), "x")

    def test_the_windows_split_test_reads_the_one_scalar_reader(self):
        import test_windows_split  # noqa: E402  the split guard, which reads its scalars with the one reader
        self.assertIs(getattr(test_windows_split, "yaml_scalar", None), getattr(workflow_steps, "yaml_scalar", None),
                      "lint/test_windows_split.py keeps its own copy of the scalar reader")


class QuotedUsesDisplay(Job):
    """A step whose uses: is not an action this runner runs prints that value as uses() reads it, so a quoted value with
    a trailing comment shows without its quotes."""

    def test_a_quoted_action_with_a_trailing_comment_shows_its_value_unquoted(self):
        rc, lines, out = self.run_job(step("tool", uses="'other/tool@v1' # c"))
        self.assertIn("(uses: other/tool@v1); CI runs it", out,
                      "the line shows the quotes, not the value uses() reads:\n" + out)

    def test_the_literal_quoted_code_check_with_a_trailing_comment_is_the_local_action(self):  # control: the action runs
        rc, lines, out = self.run_job(step("code check", uses="'./actions/code-check' # c"), args=("--base", "origin/main"))
        self.assertEqual(self.verdicts(lines), ["FAIL"],
                         "a quoted local action was not run as the repo's own action, which FAILs with no code_check.py:\n" + out)


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


class RunHeaderComments(Job):
    """A comment after a run: block header (`run: | # why`) is no part of the script. run_body reads the body, and
    bin/ci-job runs that body, so the step passes or fails on its own lines. A `#` inside a body is script text."""

    def raw_step(self, header, *body):
        return "      - name: hdr\n        run: %s\n" % header + "".join("          %s\n" % ln for ln in body) + "\n"

    def test_run_body_drops_the_comment_after_a_literal_header(self):
        self.assertEqual(run_body(self.raw_step("| # why", "true")), "true\n",
                         "run: | # why: the comment after the header was read as the script")

    def test_a_literal_header_comment_step_passes(self):
        rc, lines, out = self.run_job(self.raw_step("| # why", "true"))
        self.assertEqual((rc, self.verdicts(lines)), (0, ["PASS"]),
                         "run: | # why: the step's body is a passing command, but the header comment failed it\n" + out)

    def test_a_folded_header_comment_does_not_pass_a_failing_body(self):
        # On main the comment makes the shell read `>- # why` as a redirect: no body runs, and the step PASSes.
        rc, lines, out = self.run_job(self.raw_step(">- # why", "exit 3"))
        self.assertEqual((rc, self.verdicts(lines)), (1, ["FAIL"]),
                         "run: >- # why: the header comment hid a body that exits 3, so the step did not FAIL\n" + out)

    def test_a_lone_quote_in_a_header_comment_is_text_and_the_step_passes(self):
        rc, lines, out = self.run_job(self.raw_step("| # don't stop", "true"))
        self.assertEqual((rc, self.verdicts(lines)), (0, ["PASS"]),
                         "run: | # don't stop: a lone quote in the header comment failed the step\n" + out)

    # Controls: each passes on main and must still hold.
    def test_a_failing_body_under_a_header_comment_still_fails(self):
        rc, lines, out = self.run_job(self.raw_step("| # why", "exit 3"))
        self.assertEqual((rc, self.verdicts(lines)), (1, ["FAIL"]),
                         "run: | # why: a body that exits 3 must still FAIL under a header comment\n" + out)

    def test_a_hash_inside_a_block_body_is_script_text(self):
        rc, lines, out = self.run_job(self.raw_step("|", "echo '# kept' > kept.txt",
                                                    "test \"$(cat kept.txt)\" = '# kept'"))
        self.assertEqual((rc, self.verdicts(lines)), (0, ["PASS"]),
                         "run: |: a # inside a body line was cut as a comment\n" + out)


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


def launcher(patch):
    """A `python3 -c` launcher: the code in `patch` runs first, then ci-job runs in this process with the argv it was given."""
    return patch + "\nimport runpy, sys; sys.argv = sys.argv[1:]; runpy.run_path(sys.argv[0], run_name='__main__')\n"


# Runs ci-job with tool lookup stubbed to find every command, so a plan reads the same with or without pipx installed.
FIND_EVERY_TOOL = launcher("import shutil; shutil.which = lambda cmd, *a, **k: '/stub/' + cmd")
# Runs ci-job with os.symlink refused, as Windows does without the symlink privilege.
REFUSE_SYMLINKS = launcher("import os\ndef refused(*a, **k):\n    raise OSError(1, 'symlink refused: no symlink privilege')\nos.symlink = refused")


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
        # --base HEAD: an empty diff, so the selector picks no suite and only the lint steps are planned.
        done = plan_job("checks", "--lint", "--plan", "--base", "HEAD", cwd=os.path.join(HERE, ".."))
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

    def setUp(self):
        super().setUp()
        os.makedirs(os.path.join(self.root, "lint"))
        with open(os.path.join(self.root, "lint", "check_installed.py"), "w", encoding="utf-8", newline="\n") as f:
            f.write(LINT_SCRIPT)

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
        self.assertEqual(by_step(lines).get("Lint check"), "unknown", out)
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

    FAILS_FILE = ("lint/check_fails.py", "import sys\nprint('lint fails')\nsys.exit(1)\n")  # the one home: SuiteSteps writes it too

    def setUp(self):
        super().setUp()
        os.makedirs(os.path.join(self.root, "lint"))
        for rel, body in (("lint/check_clean.py", "print('clean')\n"), self.FAILS_FILE):
            with open(os.path.join(self.root, rel), "w", encoding="utf-8", newline="\n") as f:
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

    NO_LINT = (DEGEN[0], DEGEN[1], DEGEN[3], DEGEN[4])  # DEGEN without its one lint step

    def test_a_lint_run_that_picks_no_lint_step_is_unknown_and_exits_two(self):
        _, lines, out = plan_lint(self.root, workflow(*self.NO_LINT), extra=("--base", "origin/main"))
        self.assertEqual(selected(lines), [], out)  # the scope: the job holds no lint step for --lint to pick
        rc, lines, out = self.run_job(*self.NO_LINT, args=("--lint", "--base", "origin/main"))
        self.assertEqual(self.verdicts(lines), ["unknown"], out)
        self.assertEqual(rc, 2, out)

    def test_a_lint_step_that_runs_only_off_a_pull_request_reads_skipped_and_the_run_exits_zero(self):  # the control
        push_only = step("Push-only lint", "python3 lint/check_clean.py", **{"if": "${{ github.event_name != 'pull_request' }}"})
        rc, lines, out = self.run_job(push_only, step("Python lint", "python3 lint/check_clean.py"),
                                      args=("--lint", "--base", "origin/main"))
        self.assertEqual((rc, by_step(lines)), (0, {"Push-only lint": "skipped", "Python lint": "PASS"}), out)



def suite_text(parts, code=0, stdin_fails=None):
    """A suite that opens one file through a path constant, as hooks/test_wrappers.py opens its guard, then exits `code`.
    `parts` are the path's pieces from the suite's folder: ("..", "lint", "check_a.py") names lint/check_a.py.
    `stdin_fails`, when given, makes the suite read its stdin and exit 1 when the stdin, stripped, is that text."""
    reads = "" if stdin_fails is None else "if sys.stdin.read().strip() == %r:\n    sys.exit(1)\n" % stdin_fails
    return ("import os\nimport sys\n\nHERE = os.path.dirname(os.path.abspath(__file__))\n"
            "TARGET = os.path.join(HERE, %s)\n"
            "with open(TARGET, encoding='utf-8') as f:\n    f.read()\n"
            "print('one check ran')\n" + reads + "sys.exit(%d)\n") % (", ".join(repr(p) for p in parts), code)


class SuiteSteps(Job):
    """--lint runs a CI step (`python3 hooks|lint|merge/test_*.py`) when the selector, `hooks/mutate_guard.py
    --tests-for`, picks that suite for a file in the diff base...HEAD: a suite beside the file, or one that loads it by an
    import or a path constant. A suite the diff does not pick prints `not run`. A selector that cannot run reads unknown
    and exits 2, never a pass with no suite run. A listed file (REPORT_TARGETS) still gets each suite that loads it.
    Each fixture suite sits outside the folder of the file it opens, so only its path constant can pick it."""

    MUTATE_GUARD = os.path.join(HERE, "..", "hooks", "mutate_guard.py")
    LINT = ("--lint", "--base", "origin/main")
    WIRING = step("Wiring suite", "python3 hooks/test_wiring.py")
    CHECK_A = step("Check A suite", "python3 hooks/test_check_a.py")
    CHECK_B = step("Check B suite", "python3 hooks/test_check_b.py")
    UNDO = step("Undo suite", "python3 hooks/test_undo_loads.py")
    LINT_STEP = NotRunLines.DEGEN[2]  # a lint step that runs and passes: NotRunLines' `python3 lint/check_clean.py`
    LINT_FILE = ("lint/check_clean.py", "print('clean')\n")  # the file that step runs, as NotRunLines.setUp writes it

    def write(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

    def git(self, *a):
        LintBase.git(self, *a)  # the one home of this helper

    def make_repo(self, base, lane, lint=False, fails=False):
        """A base commit holding `base` (path -> text), origin/main at it, then a branch that writes `lane` and commits,
        so the diff base...HEAD is the files `lane` names. `lint` puts LINT_FILE in the base, so LINT_STEP runs and passes.
        `fails` puts NotRunLines.FAILS_FILE in the base, a lint step that exits 1."""
        if lint:
            base = {**base, self.LINT_FILE[0]: self.LINT_FILE[1]}
        if fails:
            base = {**base, NotRunLines.FAILS_FILE[0]: NotRunLines.FAILS_FILE[1]}
        for rel, text in base.items():
            self.write(rel, text)
        self.git("add", ".")
        self.git("commit", "-qm", "base")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.git("checkout", "-qb", "lane")
        for rel, text in lane.items():
            self.write(rel, text)
        self.git("add", ".")
        self.git("commit", "-q", "--allow-empty", "-m", "change")

    def diff(self):
        done = subprocess.run(["git", "-C", self.root, "diff", "--name-only", "origin/main...HEAD"], check=True,
                              env=ENV, capture_output=True, text=True)
        return sorted(done.stdout.split())

    def test_a_suite_that_opens_the_changed_file_by_a_path_constant_runs_and_passes(self):
        self.make_repo({"hooks/bridge.py": "V = 1\n", "hooks/test_wiring.py": suite_text(("bridge.py",))},
                       {"hooks/bridge.py": "V = 2\n"})
        self.assertEqual(self.diff(), ["hooks/bridge.py"], "the scope: the diff holds only the file the suite opens")
        rc, lines, out = self.run_job(self.WIRING, args=self.LINT)
        self.assertEqual((rc, by_step(lines)), (0, {"Wiring suite": "PASS"}),
                         "--lint must run the suite that opens the changed file by its path constant\n" + out)

    def test_a_diff_that_no_suite_opens_runs_no_suite_step(self):
        self.make_repo({"hooks/bridge.py": "V = 1\n", "hooks/test_wiring.py": suite_text(("bridge.py",)),
                        "docs/notes.md": "one\n"}, {"docs/notes.md": "two\n"}, lint=True)
        self.assertEqual(self.diff(), ["docs/notes.md"], "the scope: the diff holds a file no suite opens")
        rc, lines, out = self.run_job(self.WIRING, self.LINT_STEP, args=self.LINT)
        self.assertEqual((rc, by_step(lines)), (0, {"Wiring suite": "not run", "Python lint": "PASS"}),
                         "--lint must not run a suite that opens no changed file\n" + out)

    def test_an_empty_diff_runs_no_suite_step(self):
        self.make_repo({"hooks/bridge.py": "V = 1\n", "hooks/test_wiring.py": suite_text(("bridge.py",))}, {}, lint=True)
        self.assertEqual(self.diff(), [], "the scope: the diff is empty")
        rc, lines, out = self.run_job(self.WIRING, self.LINT_STEP, args=self.LINT)
        self.assertEqual((rc, by_step(lines)), (0, {"Wiring suite": "not run", "Python lint": "PASS"}),
                         "--lint with an empty diff must run no suite\n" + out)

    def test_a_job_whose_suite_is_not_picked_and_whose_only_lint_step_is_skipped_reads_unknown_and_exits_two(self):
        # the control is test_a_diff_that_no_suite_opens_runs_no_suite_step: the same job, with a lint step that runs and passes
        self.make_repo({"hooks/bridge.py": "V = 1\n", "hooks/test_wiring.py": suite_text(("bridge.py",)),
                        "docs/notes.md": "one\n"}, {"docs/notes.md": "two\n"}, lint=True)
        self.assertEqual(self.diff(), ["docs/notes.md"], "the scope: the diff holds a file no suite opens")
        push_only = step("Push-only lint", "python3 lint/check_clean.py", **{"if": "${{ github.event_name != 'pull_request' }}"})
        rc, lines, out = self.run_job(self.WIRING, push_only, args=self.LINT)
        self.assertEqual((by_step(lines).get("Wiring suite"), by_step(lines).get("Push-only lint")), ("not run", "skipped"),
                         "the scope: no suite is picked, and the only lint step is skipped on a pull-request run\n" + out)
        self.assertEqual(rc, 2, "a --lint run that ran no lint step must exit 2, never 0, though the job holds a suite step\n" + out)
        self.assertTrue(any(ln.startswith("unknown") and "no lint CI step" in ln for ln in lines),
                        "a --lint run that ran no lint step must print one unknown line that says so\n" + out)

    def test_a_picked_suite_that_fails_reads_fail_and_the_job_exits_one(self):
        self.make_repo({"hooks/bridge.py": "V = 1\n", "hooks/test_wiring.py": suite_text(("bridge.py",), code=1)},
                       {"hooks/bridge.py": "V = 2\n"})
        self.assertEqual(self.diff(), ["hooks/bridge.py"], "the scope: the diff holds only the file the suite opens")
        rc, lines, out = self.run_job(self.WIRING, args=self.LINT)
        self.assertEqual((rc, by_step(lines)), (1, {"Wiring suite": "FAIL"}),
                         "--lint must read a picked suite that exits 1 as FAIL, and exit 1\n" + out)

    def test_a_changed_suite_that_exits_one_reads_fail_and_the_job_exits_one(self):
        self.make_repo({"hooks/bridge.py": "V = 1\n", "hooks/test_wiring.py": suite_text(("bridge.py",))},
                       {"hooks/test_wiring.py": suite_text(("bridge.py",), code=1)})
        self.assertEqual(self.diff(), ["hooks/test_wiring.py"], "the scope: the diff holds only the suite file")
        rc, lines, out = self.run_job(self.WIRING, args=self.LINT)
        self.assertEqual((rc, by_step(lines)), (1, {"Wiring suite": "FAIL"}),
                         "--lint must run a CI step whose suite its own diff changes, and read its exit 1 as FAIL\n" + out)

    def test_a_selector_that_cannot_list_the_repository_reads_unknown_and_the_job_exits_two(self):
        self.make_repo({"hooks/bridge.py": "V = 1\n", "hooks/test_wiring.py": suite_text(("bridge.py",))},
                       {"hooks/bridge.py": "V = 2\n"})
        self.assertEqual(self.diff(), ["hooks/bridge.py"], "the scope: the diff holds only the file the suite opens")
        with open(os.path.join(self.root, ".git", "index"), "wb") as f:  # git ls-files reads the index and fails on this
            f.write(b"not an index\n")
        done = subprocess.run([sys.executable, self.MUTATE_GUARD, "--tests-for", "hooks/bridge.py"], cwd=self.root,
                              capture_output=True, text=True, env=ENV)
        self.assertEqual(done.returncode, 2, "the fixture: the selector cannot list the tracked files\n"
                         + done.stdout + done.stderr)
        rc, lines, out = self.run_job(self.WIRING, args=self.LINT)
        self.assertEqual(rc, 2, "--lint must exit 2 when the selector cannot run, never 0\n" + out)
        self.assertTrue(any(ln.startswith("unknown") for ln in lines),
                        "a selector that cannot run must print an unknown line\n" + out)
        self.assertNotIn(by_step(lines).get("Wiring suite"), ("PASS", "not run"),
                         "a selector that cannot run must not read its suite as PASS or not run\n" + out)

    def test_a_diff_touching_one_check_runs_only_the_suite_that_opens_it(self):
        self.make_repo({"lint/check_a.py": "A = 1\n", "lint/check_b.py": "B = 1\n",
                        "hooks/test_check_a.py": suite_text(("..", "lint", "check_a.py")),
                        "hooks/test_check_b.py": suite_text(("..", "lint", "check_b.py"))},
                       {"lint/check_a.py": "A = 2\n"})
        self.assertEqual(self.diff(), ["lint/check_a.py"], "the scope: the diff holds only check_a")
        rc, lines, out = self.run_job(self.CHECK_A, self.CHECK_B, args=self.LINT)
        self.assertEqual((rc, by_step(lines)), (0, {"Check A suite": "PASS", "Check B suite": "not run"}),
                         "--lint must run only the suite that opens the changed check\n" + out)

    def test_a_listed_file_still_gets_each_suite_that_opens_it_under_lint(self):
        self.make_repo({"lint/check_silent_undo.py": "U = 1\n",
                        "hooks/test_undo_loads.py": suite_text(("..", "lint", "check_silent_undo.py"))},
                       {"lint/check_silent_undo.py": "U = 2\n"})
        self.assertEqual(self.diff(), ["lint/check_silent_undo.py"], "the scope: the diff holds the listed file")
        done = subprocess.run([sys.executable, self.MUTATE_GUARD, "--tests-for", "lint/check_silent_undo.py"],
                              cwd=self.root, capture_output=True, text=True, env=ENV)
        self.assertEqual(done.stdout.split(), ["lint/test_check_silent_undo.py"],
                         "the fixture: --tests-for prints a listed file's REPORT_TARGETS suites only\n"
                         + done.stdout + done.stderr)
        rc, lines, out = self.run_job(self.UNDO, args=self.LINT)
        self.assertEqual((rc, by_step(lines)), (0, {"Undo suite": "PASS"}),
                         "--lint must still run a suite that opens a file listed in REPORT_TARGETS\n" + out)

    PREP_WIRING = step("Wiring suite", "echo prep\npython3 hooks/test_wiring.py")
    WIRING_WITH_ARG = step("Wiring suite", "python3 hooks/test_wiring.py -v")
    SELECTOR_LIMIT = 120  # seconds a hanging selector may hold ci-job before the case fails: a bound on the wait, not an assert on time

    def stub_ci_job(self, selector):
        """A copy of bin/ci-job in its own root, with `selector` as its hooks/mutate_guard.py: ci-job asks for the selector
        beside its own folder, so the copy gets the stub and no other. Each other file it reads is a link to this checkout's."""
        if os.name == "nt":
            self.skipTest("the stub root links this checkout's files, and Windows grants no symlink here")
        root = os.path.join(self.root, "stub")
        for sub in ("bin", "hooks"):
            os.makedirs(os.path.join(root, sub))
        shutil.copy(CI_JOB, os.path.join(root, "bin", "ci-job"))
        for sub, skipped in (("bin", "ci-job"), ("hooks", "mutate_guard.py")):
            for name in os.listdir(os.path.join(CHECKOUT, sub)):
                if name != skipped:
                    os.symlink(os.path.join(CHECKOUT, sub, name), os.path.join(root, sub, name))
        os.symlink(os.path.join(CHECKOUT, "lint"), os.path.join(root, "lint"))  # workflow_steps, the step parser
        with open(os.path.join(root, "hooks", "mutate_guard.py"), "w", encoding="utf-8", newline="\n") as f:
            f.write(selector)
        return os.path.join(root, "bin", "ci-job")

    def test_a_picked_suite_under_a_multi_line_step_runs_the_whole_step_and_passes(self):
        self.make_repo({"hooks/bridge.py": "V = 1\n", "hooks/test_wiring.py": suite_text(("bridge.py",))},
                       {"hooks/bridge.py": "V = 2\n"})
        self.assertEqual(self.diff(), ["hooks/bridge.py"], "the scope: the diff holds only the file the suite opens")
        rc, lines, out = self.run_job(self.PREP_WIRING, args=self.LINT)
        self.assertEqual((rc, by_step(lines)), (0, {"Wiring suite": "PASS"}),
                         "--lint must run a picked suite whose step has a line before its python3 line, as CI runs the whole step\n" + out)

    def test_a_picked_suite_under_a_multi_line_step_that_exits_one_reads_fail_and_the_job_exits_one(self):
        self.make_repo({"hooks/bridge.py": "V = 1\n", "hooks/test_wiring.py": suite_text(("bridge.py",), code=1)},
                       {"hooks/bridge.py": "V = 2\n"})
        self.assertEqual(self.diff(), ["hooks/bridge.py"], "the scope: the diff holds only the file the suite opens")
        rc, lines, out = self.run_job(self.PREP_WIRING, args=self.LINT)
        self.assertEqual((rc, by_step(lines)), (1, {"Wiring suite": "FAIL"}),
                         "--lint must read a picked suite's exit 1 under a multi-line step as FAIL, and exit 1\n" + out)

    NPM_GUARD = "[ -d node_modules/typescript ] || npm ci --ignore-scripts --no-audit --no-fund"  # checks.yml's preamble
    GUARDED_WIRING = step("Wiring suite", NPM_GUARD + "\npython3 hooks/test_wiring.py")
    BLOCK_WIRING = step("Wiring suite", "if [ ! -d node_modules ]; then npm ci; fi\npython3 hooks/test_wiring.py")

    def test_a_picked_ci_step_whose_guard_preamble_npm_fails_reads_unknown_and_the_job_exits_two(self):
        self.make_repo({"hooks/bridge.py": "V = 1\n", "hooks/test_wiring.py": suite_text(("bridge.py",))},
                       {"hooks/bridge.py": "V = 2\n"})
        self.assertEqual(self.diff(), ["hooks/bridge.py"], "the scope: the diff holds only the file the suite opens")
        env = self.stub_path(npm='echo "npm: stub install failed" >&2\nexit 1')
        rc, lines, out = self.run_job(self.GUARDED_WIRING, args=self.LINT, env=env)
        self.assertEqual((rc, by_step(lines)), (2, {"Wiring suite": "unknown"}),
                         "--lint must read a failed npm ci in the guard preamble of a picked CI step as unknown, never FAIL\n" + out)

    def test_a_picked_ci_step_whose_guard_preamble_npm_passes_and_whose_suite_exits_one_reads_fail(self):
        self.make_repo({"hooks/bridge.py": "V = 1\n", "hooks/test_wiring.py": suite_text(("bridge.py",), code=1)},
                       {"hooks/bridge.py": "V = 2\n"})
        self.assertEqual(self.diff(), ["hooks/bridge.py"], "the scope: the diff holds only the file the suite opens")
        env = self.stub_path(npm=self.NPM_OK)
        rc, lines, out = self.run_job(self.GUARDED_WIRING, args=self.LINT, env=env)
        self.assertEqual(self.npm_calls(), "ci --ignore-scripts --no-audit --no-fund\n",
                         "the fixture: the guard runs npm ci, since node_modules/typescript is absent\n" + out)
        self.assertEqual((rc, by_step(lines)), (1, {"Wiring suite": "FAIL"}),
                         "--lint must read a picked suite's exit 1 behind a guard preamble whose npm ci passes as FAIL, and exit 1\n"
                         + out)

    def test_a_picked_ci_step_whose_guard_preamble_npm_passes_and_whose_suite_passes_reads_pass(self):
        self.make_repo({"hooks/bridge.py": "V = 1\n", "hooks/test_wiring.py": suite_text(("bridge.py",))},
                       {"hooks/bridge.py": "V = 2\n"})
        self.assertEqual(self.diff(), ["hooks/bridge.py"], "the scope: the diff holds only the file the suite opens")
        env = self.stub_path(npm=self.NPM_OK)
        rc, lines, out = self.run_job(self.GUARDED_WIRING, args=self.LINT, env=env)
        self.assertEqual(self.npm_calls(), "ci --ignore-scripts --no-audit --no-fund\n",
                         "the fixture: the guard runs npm ci, since node_modules/typescript is absent\n" + out)
        self.assertEqual((rc, by_step(lines)), (0, {"Wiring suite": "PASS"}),
                         "--lint must read a picked CI step behind a guard preamble whose npm ci passes, and whose suite passes, as PASS\n"
                         + out)

    def test_a_picked_ci_step_whose_preamble_prints_no_newline_and_whose_suite_exits_one_reads_fail(self):
        # the control is test_a_picked_ci_step_whose_guard_preamble_npm_passes_and_whose_suite_exits_one_reads_fail: the same
        # suite behind a preamble that ends in a newline. Here the preamble prints with no newline, so the marker lands mid-line.
        self.make_repo({"hooks/bridge.py": "V = 1\n", "hooks/test_wiring.py": suite_text(("bridge.py",), code=1)},
                       {"hooks/bridge.py": "V = 2\n"})
        self.assertEqual(self.diff(), ["hooks/bridge.py"], "the scope: the diff holds only the file the suite opens")
        rc, lines, out = self.run_job(step("Wiring suite", "printf x\npython3 hooks/test_wiring.py"), args=self.LINT)
        self.assertEqual((rc, by_step(lines)), (1, {"Wiring suite": "FAIL"}),
                         "--lint must read a picked suite's exit 1 behind a preamble that prints with no trailing newline as FAIL, "
                         "and exit 1\n" + out)

    def test_a_picked_ci_step_whose_npm_sits_in_a_skipped_if_block_reads_the_suite_verdict(self):
        self.make_repo({"hooks/bridge.py": "V = 1\n", "hooks/test_wiring.py": suite_text(("bridge.py",), code=1)},
                       {"hooks/bridge.py": "V = 2\n"})
        self.assertEqual(self.diff(), ["hooks/bridge.py"], "the scope: the diff holds only the file the suite opens")
        os.makedirs(os.path.join(self.root, "node_modules"))  # the if block is skipped: its npm ci never runs
        env = self.path_without("npm")
        self.assertIsNone(shutil.which("npm", path=env["PATH"]), "the fixture: npm is not on the step's PATH")
        missing = [tool for tool in ("bash", "git", "python3") if not shutil.which(tool, path=env["PATH"])]
        if missing:
            self.skipTest("without npm on PATH, %s is missing, so this case cannot run here" % ", ".join(missing))
        rc, lines, out = self.run_job(self.BLOCK_WIRING, args=self.LINT, env=env)
        self.assertEqual((rc, by_step(lines)), (1, {"Wiring suite": "FAIL"}),
                         "--lint must not read a CI step as unknown for an npm ci in an if block that is skipped: npm never runs\n" + out)

    def test_a_picked_suite_whose_step_passes_it_an_argument_runs_and_passes(self):
        self.make_repo({"hooks/bridge.py": "V = 1\n", "hooks/test_wiring.py": suite_text(("bridge.py",))},
                       {"hooks/bridge.py": "V = 2\n"})
        self.assertEqual(self.diff(), ["hooks/bridge.py"], "the scope: the diff holds only the file the suite opens")
        rc, lines, out = self.run_job(self.WIRING_WITH_ARG, args=self.LINT)
        self.assertEqual((rc, by_step(lines)), (0, {"Wiring suite": "PASS"}),
                         "--lint must run a picked suite whose step passes it an argument\n" + out)

    def test_a_suite_that_reaches_a_changed_module_through_an_import_runs_and_passes(self):
        self.make_repo({"hooks/leaf.py": "V = 1\n", "hooks/entry.py": "import leaf\n\nVALUE = leaf.V\n",
                        "hooks/test_wiring.py": suite_text(("entry.py",))},
                       {"hooks/leaf.py": "V = 2\n"})
        self.assertEqual(self.diff(), ["hooks/leaf.py"], "the scope: the diff holds only leaf.py, which no suite opens by name")
        rc, lines, out = self.run_job(self.WIRING, args=self.LINT)
        self.assertEqual((rc, by_step(lines)), (0, {"Wiring suite": "PASS"}),
                         "--lint must run a suite that opens entry.py, which imports the changed leaf.py\n" + out)

    def test_a_selector_that_hangs_reads_unknown_and_the_job_exits_two_within_the_bound(self):
        self.make_repo({"hooks/bridge.py": "V = 1\n", "hooks/test_wiring.py": suite_text(("bridge.py",))},
                       {"hooks/bridge.py": "V = 2\n"})
        self.assertEqual(self.diff(), ["hooks/bridge.py"], "the scope: the diff holds only the file the suite opens")
        argv, env = self.job_call(self.WIRING, args=self.LINT, env={"PYTHONDONTWRITEBYTECODE": "1"},
                                  script=self.stub_ci_job("import time\ntime.sleep(3600)\n"))
        # Its own session, so the hung selector, a child of ci-job, is killed with it on every path.
        proc = subprocess.Popen(argv, cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
                                start_new_session=True)
        out = err = None
        try:
            out, err = proc.communicate(timeout=self.SELECTOR_LIMIT)
        except subprocess.TimeoutExpired:
            pass
        finally:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
        if out is None:
            self.fail("ci-job ran past %d s while its selector hung: it must print unknown and exit 2 within a bound"
                      % self.SELECTOR_LIMIT)
        lines = [ln for ln in out.splitlines() if not ln.startswith("log=")]
        self.assertEqual((proc.returncode, by_step(lines)), (2, {"Wiring suite": "unknown"}),
                         "a selector that hangs must read as unknown on the CI step, and the job must exit 2\n" + out + err)

    def test_a_picked_suite_whose_step_is_only_in_another_job_is_one_not_run_line_that_names_it(self):
        self.make_repo({"hooks/bridge.py": "V = 1\n", "hooks/test_wiring.py": suite_text(("bridge.py",))},
                       {"hooks/bridge.py": "V = 2\n"}, lint=True)
        self.assertEqual(self.diff(), ["hooks/bridge.py"], "the scope: the diff holds only the file the suite opens")
        rc, lines, out = self.run_job(step("Docs", "echo docs"), self.LINT_STEP, job="checks", other=[self.WIRING],
                                      args=self.LINT)
        named = [ln for ln in lines if "Wiring suite" in ln or "hooks/test_wiring.py" in ln]
        self.assertEqual(len(named), 1,
                         "--lint must print one line for a picked suite whose step is only in job other, never silence\n" + out)
        self.assertTrue(NOT_RUN.match(named[0]), "that line must start with `not run`\n" + out)
        self.assertRegex(named[0], r"\bother\b", "that line must name job other\n" + out)
        self.assertEqual(rc, 0, "a not-run line never moves the exit code\n" + out)

    def test_the_same_suite_in_the_job_that_runs_is_run_and_passes(self):  # the control for the case above
        self.make_repo({"hooks/bridge.py": "V = 1\n", "hooks/test_wiring.py": suite_text(("bridge.py",))},
                       {"hooks/bridge.py": "V = 2\n"})
        self.assertEqual(self.diff(), ["hooks/bridge.py"], "the scope: the diff holds only the file the suite opens")
        rc, lines, out = self.run_job(self.WIRING, job="checks", other=[step("Docs", "echo docs")], args=self.LINT)
        self.assertEqual((rc, by_step(lines).get("Wiring suite")), (0, "PASS"),
                         "--lint must run a picked suite whose step is in the job asked for\n" + out)

    def test_a_picked_suite_behind_a_preamble_line_ending_in_and_reads_fail_as_ci_does(self):
        self.make_repo({"hooks/bridge.py": "V = 1\n", "hooks/test_wiring.py": suite_text(("bridge.py",))},
                       {"hooks/bridge.py": "V = 2\n"})
        self.assertEqual(self.diff(), ["hooks/bridge.py"], "the scope: the diff holds only the file the suite opens")
        body = "false &&\npython3 hooks/test_wiring.py"
        ci = subprocess.run(["bash", "-e", "-c", body], cwd=self.root, capture_output=True, text=True, env=ENV)
        self.assertNotEqual(ci.returncode, 0, "the fixture: CI's step fails, since `false &&` skips the suite\n"
                            + ci.stdout + ci.stderr)
        rc, lines, out = self.run_job(step("Wiring suite", body), args=self.LINT)
        self.assertIn(by_step(lines).get("Wiring suite"), ("FAIL", "unknown"),
                      "--lint read a picked suite behind `false &&` as PASS: the marker joined the `&&`, so the suite ran, "
                      "and CI's step, which skips it, fails\n" + out)
        self.assertNotEqual(rc, 0, out)

    def test_a_picked_suite_behind_a_passing_preamble_line_ending_in_and_reads_pass(self):
        # the control for the case above: `true &&` runs the suite, as CI does, and the suite passes
        self.make_repo({"hooks/bridge.py": "V = 1\n", "hooks/test_wiring.py": suite_text(("bridge.py",))},
                       {"hooks/bridge.py": "V = 2\n"})
        self.assertEqual(self.diff(), ["hooks/bridge.py"], "the scope: the diff holds only the file the suite opens")
        rc, lines, out = self.run_job(step("Wiring suite", "true &&\npython3 hooks/test_wiring.py"), args=self.LINT)
        self.assertEqual((rc, by_step(lines)), (0, {"Wiring suite": "PASS"}),
                         "--lint must run a picked suite behind `true &&`, as CI does, and read its PASS\n" + out)

    def test_a_picked_suite_behind_a_preamble_line_ending_in_or_is_not_read_as_fail_when_ci_skips_it(self):
        self.make_repo({"hooks/bridge.py": "V = 1\n", "hooks/test_wiring.py": suite_text(("bridge.py",), code=1)},
                       {"hooks/bridge.py": "V = 2\n"})
        self.assertEqual(self.diff(), ["hooks/bridge.py"], "the scope: the diff holds only the file the suite opens")
        body = "true ||\npython3 hooks/test_wiring.py"
        ci = subprocess.run(["bash", "-e", "-c", body], cwd=self.root, capture_output=True, text=True, env=ENV)
        self.assertEqual((ci.returncode, "one check ran" in ci.stdout), (0, False),
                         "the fixture: CI's step passes with the suite skipped, since `true ||` succeeds\n" + ci.stdout + ci.stderr)
        rc, lines, out = self.run_job(step("Wiring suite", body), args=self.LINT)
        self.assertNotEqual(by_step(lines).get("Wiring suite"), "FAIL",
                            "--lint read a suite that CI skips behind `true ||` as FAIL: the marker joined the `||`, "
                            "so the suite ran and failed\n" + out)

    def test_a_picked_suite_behind_a_failing_preamble_line_ending_in_or_still_runs_and_reads_pass(self):
        # the control for the case above: `false ||` runs the suite, as CI does, so a passing suite reads PASS
        self.make_repo({"hooks/bridge.py": "V = 1\n", "hooks/test_wiring.py": suite_text(("bridge.py",))},
                       {"hooks/bridge.py": "V = 2\n"})
        self.assertEqual(self.diff(), ["hooks/bridge.py"], "the scope: the diff holds only the file the suite opens")
        rc, lines, out = self.run_job(step("Wiring suite", "false ||\npython3 hooks/test_wiring.py"), args=self.LINT)
        self.assertEqual((rc, by_step(lines)), (0, {"Wiring suite": "PASS"}),
                         "--lint must run a picked suite behind `false ||`, as CI does, and read its PASS\n" + out)

    def test_a_picked_suite_behind_a_preamble_line_ending_in_pipe_reads_fail_as_ci_does(self):
        suite = suite_text(("bridge.py",), stdin_fails="bad")
        self.make_repo({"hooks/bridge.py": "V = 1\n", "hooks/test_wiring.py": suite}, {"hooks/bridge.py": "V = 2\n"})
        self.assertEqual(self.diff(), ["hooks/bridge.py"], "the scope: the diff holds only the file the suite opens")
        body = "printf bad |\npython3 hooks/test_wiring.py"
        ci = subprocess.run(["bash", "-e", "-c", body], cwd=self.root, capture_output=True, text=True, env=ENV)
        self.assertNotEqual(ci.returncode, 0, "the fixture: CI's step fails, since the suite reads `bad` from the pipe\n"
                            + ci.stdout + ci.stderr)
        rc, lines, out = self.run_job(step("Wiring suite", body), args=self.LINT, stdin=subprocess.DEVNULL)
        self.assertIn(by_step(lines).get("Wiring suite"), ("FAIL", "unknown"),
                      "--lint read a picked suite behind `printf bad |` as PASS: the marker cut the pipe, so the suite read "
                      "no `bad` and passed, and CI's step fails\n" + out)
        self.assertNotEqual(rc, 0, out)

    def test_a_picked_suite_behind_a_pipe_that_feeds_it_ok_reads_pass(self):
        # the control for the case above: the same suite behind `printf ok |` reads `ok`, not `bad`, and passes
        suite = suite_text(("bridge.py",), stdin_fails="bad")
        self.make_repo({"hooks/bridge.py": "V = 1\n", "hooks/test_wiring.py": suite}, {"hooks/bridge.py": "V = 2\n"})
        self.assertEqual(self.diff(), ["hooks/bridge.py"], "the scope: the diff holds only the file the suite opens")
        body = "printf ok |\npython3 hooks/test_wiring.py"
        ci = subprocess.run(["bash", "-e", "-c", body], cwd=self.root, capture_output=True, text=True, env=ENV)
        self.assertEqual(ci.returncode, 0, "the fixture: CI's step passes when the pipe feeds `ok`\n" + ci.stdout + ci.stderr)
        rc, lines, out = self.run_job(step("Wiring suite", body), args=self.LINT, stdin=subprocess.DEVNULL)
        self.assertEqual((rc, by_step(lines)), (0, {"Wiring suite": "PASS"}),
                         "--lint must run a picked suite behind `printf ok |`, as CI does, and read its PASS\n" + out)

    def test_a_picked_suite_whose_preamble_fails_does_not_block_the_lint_step_after_it(self):
        self.make_repo({"hooks/bridge.py": "V = 1\n", "hooks/test_wiring.py": suite_text(("bridge.py",))},
                       {"hooks/bridge.py": "V = 2\n"}, fails=True)
        self.assertEqual(self.diff(), ["hooks/bridge.py"], "the scope: the diff holds only the file the suite opens")
        rc, lines, out = self.run_job(step("Wiring suite", "false\npython3 hooks/test_wiring.py"),
                                      step("Lint check", "python3 lint/check_fails.py"), args=self.LINT)
        self.assertEqual(by_step(lines).get("Wiring suite"), "unknown",
                         "the scope: a failed line before the suite reads the suite unknown\n" + out)
        self.assertEqual(by_step(lines).get("Lint check"), "FAIL",
                         "a failed preamble of a picked suite must not block the lint step after it: --lint read that "
                         "lint step as something other than FAIL\n" + out)
        self.assertEqual(rc, 1, out)

    def test_a_picked_suite_whose_preamble_passes_does_not_stop_the_lint_step_after_it_from_failing(self):
        # the control for the case above: `true` before the suite, so the lint step after it runs and reads its own FAIL
        self.make_repo({"hooks/bridge.py": "V = 1\n", "hooks/test_wiring.py": suite_text(("bridge.py",))},
                       {"hooks/bridge.py": "V = 2\n"}, fails=True)
        self.assertEqual(self.diff(), ["hooks/bridge.py"], "the scope: the diff holds only the file the suite opens")
        rc, lines, out = self.run_job(step("Wiring suite", "true\npython3 hooks/test_wiring.py"),
                                      step("Lint check", "python3 lint/check_fails.py"), args=self.LINT)
        self.assertEqual((rc, by_step(lines)), (1, {"Wiring suite": "PASS", "Lint check": "FAIL"}), out)


RV = '''import os


def arrive(name):
    open(name, "w").close()


def wait_for(*names):
    """Waits, with no bound, until every named file exists: the marker is the only exit."""
    yield_cpu = getattr(os, "sched_yield", lambda: None)
    while not all(os.path.exists(n) for n in names):
        yield_cpu()
'''


def meet(mine, *others):
    """Lint body: announce `mine`, then wait, with no bound, for each of `others` to announce."""
    names = ", ".join("'arrived-%s'" % o for o in others)
    return "rv.arrive('arrived-%s')\nrv.wait_for(%s)\n" % (mine, names)


def done(name):
    """Lint body: announce that `name` is finished, as its last act."""
    return "rv.arrive('done-%s')\n" % name


def cpus(n):
    """ci-job's launch with os.cpu_count() reporting `n`, None included."""
    return ("-c", launcher("import os\nos.cpu_count = lambda: %r" % (n,)))


def normal(lines):
    """Each output line with its shell and script, its seconds and its log path fixed, one space between words."""
    out = []
    for ln in lines:
        ln = re.sub(r"\S*bash -e \S+\.sh", "SHELL", ln)
        ln = re.sub(r"\(\d+\.\d+s\)", "(N)", ln)
        ln = re.sub(r"log=\S+", "log=L", ln)
        out.append(re.sub(r"\s+", " ", ln))
    return out


class ParallelLint(Job):
    """--lint runs its lint CI steps at once, up to a worker count: CI_JOB_LINT_WORKERS when that is a positive int, else
    min(os.cpu_count(), 4), at least 1 (the cpu cases patch os.cpu_count). Steps prove they overlap by rendezvous on marker
    files. No wait has a bound, no count and no clock: each ends only on its marker. So a wrong build (serial, or a cap
    that lets too many run) blocks instead of failing, and the CI job's own timeout reds it. Verdict lines, the summary
    and each lint step's log lines keep workflow order. An install CI step is a barrier. Plain runs, --step and --plan
    stay serial."""

    INSTALL = "touch installed.marker\n"
    L3_CHECKS = ("if not os.path.exists('installed.marker'):\n"
                 "    print('install not finished when this lint step started')\n    sys.exit(1)\n"
                 "print('install finished before this lint step started')\n")

    def setUp(self):
        super().setUp()
        os.makedirs(os.path.join(self.root, "lint"))
        with open(os.path.join(self.root, "lint", "rv.py"), "w", encoding="utf-8", newline="\n") as f:
            f.write(RV)

    def script(self, name, body):
        """A lint script under lint/, its imports first."""
        with open(os.path.join(self.root, "lint", name + ".py"), "w", encoding="utf-8", newline="\n") as f:
            f.write("import os, rv, sys\n" + body)

    def lint(self, name, body):
        """A lint CI step with its own script: its whole run: is `python3 lint/<name>.py`."""
        self.script(name, body)
        return step(name, "python3 lint/%s.py" % name)

    def rendezvous_steps(self, names):
        """One lint CI step per name; each waits for every other name, then announces it is done."""
        return [self.lint(n, meet(n, *[m for m in names if m != n]) + done(n)) for n in names]

    def check_all_pass(self, names, **kw):
        rc, lines, out = self.run_lint(*self.rendezvous_steps(names), **kw)
        self.assertEqual(list(by_step(lines).items()), [(n, "PASS") for n in names], out)
        self.assertEqual(rc, 0, out)

    def check_cap(self, names, **kw):
        """Under the cap every name passes. The last name starts only after a worker has finished, and a finished name has
        written its done marker, so the last name finds one. Run all at once, the last name may find none and read FAIL.
        No marker can hold a finished name back, so that red is a race, not a forced one."""
        group, last = names[:-1], names[-1]
        steps = [self.lint(g, meet(g, *[m for m in group if m != g]) + done(g)) for g in group]
        freed = " or ".join("os.path.exists('done-%s')" % g for g in group)
        steps.append(self.lint(last, "if not (%s):\n    print('no worker had finished when %s started: the cap did not hold')\n"
                                     "    sys.exit(1)\n" % (freed, last) + meet(last, *group) + done(last)))
        rc, lines, out = self.run_lint(*steps, **kw)
        self.assertEqual(list(by_step(lines).items()), [(n, "PASS") for n in names], out)
        self.assertEqual(rc, 0, out)

    def fresh_run(self):
        """Removes the last run's files, so a second run in one case starts with no marker of the first."""
        for name in os.listdir(self.root):
            if name not in (".git", "lint"):
                path = os.path.join(self.root, name)
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
        for name in os.listdir(os.path.join(self.root, "lint")):
            path = os.path.join(self.root, "lint", name)
            if name != "rv.py":
                if os.path.isdir(path):  # a step's __pycache__ when bytecode is written
                    shutil.rmtree(path)
                else:
                    os.remove(path)

    def read(self, rel):
        try:
            with open(os.path.join(self.root, rel), encoding="utf-8", errors="replace") as f:
                return f.read()
        except OSError:
            return "(no %s)" % rel

    def run_lint(self, *steps, workers=None, args=("--lint", "--base", "origin/main"), launch=(), env=None):
        """(rc, stdout lines, output). The lines are ci-job's stdout as printed, log= included (run_job strips it). The
        output adds stderr and the run's verdict log, so a failure names the cause the step itself kept. self.err_lines
        holds ci-job's stderr lines, its `start:` lines included. No timeout: a wrong build blocks."""
        extra = {"CI_JOB_LINT_WORKERS": str(workers)} if workers is not None else {}
        argv, run_env = self.job_call(*steps, args=args, env={**extra, **(env or {})}, launch=launch)
        proc = subprocess.run(argv, cwd=self.root, capture_output=True, text=True, env=run_env)
        self.err_lines = proc.stderr.splitlines()
        return proc.returncode, proc.stdout.splitlines(), \
            proc.stdout + proc.stderr + "\n--- verdict log ---\n" + self.read("verdict.log")

    def test_two_workers_run_a_pair_at_once(self):
        self.check_all_pass(["a", "b"], workers=2)

    def test_with_two_cpus_the_default_runs_a_pair_at_once(self):
        self.check_all_pass(["a", "b"], launch=cpus(2))

    def test_two_workers_never_run_three_at_once(self):
        self.check_cap(["a", "b", "c"], workers=2)

    def test_with_two_cpus_the_default_never_runs_three_at_once(self):
        self.check_cap(["a", "b", "c"], launch=cpus(2))

    def test_a_worker_count_of_four_runs_four_steps_at_once_even_on_a_two_cpu_machine(self):
        self.check_all_pass(["w1", "w2", "w3", "w4"], workers=4, launch=cpus(2))

    def test_with_eight_cpus_the_default_runs_four_at_once(self):
        self.check_all_pass(["w1", "w2", "w3", "w4"], launch=cpus(8))

    def test_with_eight_cpus_the_default_never_runs_five_at_once(self):
        self.check_cap(["w1", "w2", "w3", "w4", "w5"], launch=cpus(8))

    def test_an_invalid_worker_count_falls_back_to_the_default(self):
        for value in ("0", "abc"):
            self.fresh_run()
            rc, lines, out = self.run_lint(*self.rendezvous_steps(["a", "b"]), workers=value, launch=cpus(4))
            self.assertEqual(list(by_step(lines).items()), [("a", "PASS"), ("b", "PASS")],
                             "CI_JOB_LINT_WORKERS=%s did not fall back to the default worker count:\n%s" % (value, out))
            self.assertEqual(rc, 0, out)

    def test_verdict_lines_and_summary_keep_workflow_order_whatever_order_steps_finish(self):
        steps = (self.lint("first", "rv.wait_for('done-third')\n"),
                 self.lint("second", "print('second')\n"),
                 self.lint("third", done("third")))
        rc, lines, out = self.run_lint(*steps, workers=3)
        self.assertEqual(list(by_step(lines).items()), [("first", "PASS"), ("second", "PASS"), ("third", "PASS")], out)
        self.assertEqual(rc, 0, out)
        self.assertEqual((lines[-2], lines[-1][:4]), ("summary: ran 3 of 3 steps", "log="), out)

    def test_the_log_keeps_each_step_output_in_workflow_order(self):
        # alpha, first in workflow order, waits for beta's done marker. A log appended in finish order usually puts beta's
        # output first, since beta's exit and alpha's exit race after their markers: the marker orders the writes, not the exits.
        steps = (self.lint("alpha", "rv.wait_for('done-beta')\nprint('ALPHA-OUTPUT')\n"),
                 self.lint("beta", "print('BETA-OUTPUT')\n" + done("beta")),
                 self.lint("gamma", "print('GAMMA-OUTPUT')\n"))
        rc, lines, out = self.run_lint(*steps, workers=3)
        self.assertEqual(list(by_step(lines).items()), [("alpha", "PASS"), ("beta", "PASS"), ("gamma", "PASS")], out)
        self.assertEqual(rc, 0, out)
        log = self.read("verdict.log")
        self.assertTrue(0 <= log.find("ALPHA-OUTPUT") < log.find("BETA-OUTPUT") < log.find("GAMMA-OUTPUT"),
                        "the log does not keep the step order:\n" + out)

    def test_a_step_that_fails_fast_does_not_stop_the_others_and_the_log_is_the_run_log(self):
        steps = (self.lint("f", "print('F-OUTPUT')\nsys.exit(1)\n"),
                 self.lint("p1", meet("p1", "p2") + "print('P1-OUTPUT')\n" + done("p1")),
                 self.lint("p2", meet("p2", "p1") + "print('P2-OUTPUT')\n" + done("p2")),
                 self.lint("u", "print('U-OUTPUT')\nsys.exit(127)\n"))
        rc, lines, out = self.run_lint(*steps, workers=4)
        self.assertEqual(list(by_step(lines).items()), [("f", "FAIL"), ("p1", "PASS"), ("p2", "PASS"), ("u", "unknown")], out)
        self.assertEqual(rc, 1, out)
        f_line = next(ln for ln in lines if ln.startswith("FAIL") and " f: " in ln)
        self.assertIn("log=%s" % self.log, f_line, "a parallel step's line does not name the run's log:\n" + out)
        self.assertEqual(lines[-1], "log=%s" % self.log, "the run's log= line is not the run's log:\n" + out)
        log = self.read("verdict.log")
        self.assertEqual(log.count("=== verdict run"), 4, "the run's log does not hold each step's own lines:\n" + log)
        self.assertTrue(all(tok in log for tok in ("F-OUTPUT", "P1-OUTPUT", "P2-OUTPUT", "U-OUTPUT")),
                        "the run's log is missing a step's output:\n" + log)

    def test_a_log_that_cannot_join_the_run_log_is_named_on_stderr_and_kept(self):
        # VERDICT_LOG is a directory, so no CI step's copy can join it. Each verdict and the exit code stay as they are; ci-job
        # names each kept log on stderr, and each kept log holds its own CI step's output.
        os.makedirs(self.log)
        steps = (self.lint("one", "print('ONE-OUTPUT')\n"), self.lint("two", "print('TWO-OUTPUT')\n"))
        rc, lines, out = self.run_lint(*steps, workers=2)
        self.assertEqual(list(by_step(lines).items()), [("one", "PASS"), ("two", "PASS")], out)
        self.assertEqual(rc, 0, out)
        kept = {}
        for ln in self.err_lines:
            m = re.match(r"ci-job: could not add the log of CI step (\S+) to the run's log; its output is kept in (.+)$", ln)
            if m:
                kept[m.group(1)] = m.group(2)
        self.assertEqual(sorted(kept), ["one", "two"], "a failed copy is not named on stderr:\n" + out)
        for name, token in (("one", "ONE-OUTPUT"), ("two", "TWO-OUTPUT")):
            path = kept[name]
            self.addCleanup(shutil.rmtree, os.path.dirname(path), True)
            self.assertTrue(os.path.exists(path), "the kept log named for %s is missing: %s\n%s" % (name, path, out))
            with open(path, encoding="utf-8", errors="replace") as f:
                self.assertIn(token, f.read(), "the kept log for %s does not hold its output\n%s" % (name, out))

    def test_an_unknown_step_alone_exits_two_while_the_others_pass(self):
        steps = (self.lint("u", "print('U-OUTPUT')\nsys.exit(127)\n"),) + tuple(self.rendezvous_steps(["p1", "p2"]))
        rc, lines, out = self.run_lint(*steps, workers=4)
        self.assertEqual(list(by_step(lines).items()), [("u", "unknown"), ("p1", "PASS"), ("p2", "PASS")], out)
        self.assertEqual(rc, 2, out)

    def test_a_failing_neighbours_runner_marker_is_not_read_by_a_passing_parallel_step(self):
        steps = (self.lint("noisy", "rv.wait_for('arrived-clean')\nprint('** TEST FAILED **')\n"
                                    "rv.arrive('printed-noisy')\nsys.exit(1)\n"),
                 self.lint("clean", "rv.arrive('arrived-clean')\nrv.wait_for('printed-noisy')\nprint('CLEAN-OUTPUT')\n"))
        rc, lines, out = self.run_lint(*steps, workers=2)
        self.assertEqual(list(by_step(lines).items()), [("noisy", "FAIL"), ("clean", "PASS")], out)
        self.assertEqual(rc, 1, out)

    def test_a_step_that_exits_127_is_unknown_and_its_neighbour_passes(self):
        steps = (self.lint("missing", meet("missing", "clean") + "rv.arrive('printed-missing')\nsys.exit(127)\n"),
                 self.lint("clean", "rv.arrive('arrived-clean')\nrv.wait_for('arrived-missing', 'printed-missing')\n"
                                    "print('CLEAN-OUTPUT')\n"))
        rc, lines, out = self.run_lint(*steps, workers=2)
        self.assertEqual(list(by_step(lines).items()), [("missing", "unknown"), ("clean", "PASS")], out)
        self.assertEqual(rc, 2, out)
        self.assertIn("tool missing", next(ln for ln in lines if ln.startswith("unknown")), out)

    def test_a_command_missing_at_run_time_is_unknown_and_its_neighbour_passes(self):
        # plan checks only a line's first word, so the argument's command substitution reaches the shell at run time:
        # the shell prints its real `command not found` line into this step's own log, and the python still exits 0.
        self.script("gate", "rv.arrive('arrived-miss')\nrv.wait_for('arrived-clean')\nrv.arrive('gate-ok')\n")
        self.script("miss", "rv.arrive('printed-miss')\n")
        steps = (step("miss", 'python3 lint/miss.py "$(python3 lint/gate.py)" $(no-such-tool-c69 --x)'),
                 self.lint("clean", "rv.arrive('arrived-clean')\nrv.wait_for('printed-miss')\n"
                                    "if not os.path.exists('gate-ok'):\n    sys.exit(1)\n"
                                    "print('CLEAN-OUTPUT')\n"))
        rc, lines, out = self.run_lint(*steps, workers=2)
        self.assertEqual(list(by_step(lines).items()), [("miss", "unknown"), ("clean", "PASS")], out)
        self.assertEqual(rc, 2, out)
        self.assertIn("no-such-tool-c69", next(ln for ln in lines if ln.startswith("unknown")), out)

    def install_steps(self, install_body, l3_body):
        """Two lint CI steps that must overlap, then an install CI step, then a lint CI step that reads what it made."""
        env = InstallSteps.stub_path(self, npm=install_body)  # the npm stub: InstallSteps holds the one home
        steps = (self.lint("l1", meet("l1", "l2")), self.lint("l2", meet("l2", "l1")),
                 step("Install deps", "npm ci"), self.lint("l3", l3_body))
        _, plan_lines, plan_out = plan_lint(self.root, workflow(*steps), extra=("--base", "origin/main"))
        self.assertEqual(would_run(plan_lines), ["Install deps", "l1", "l2", "l3"], plan_out)
        return self.run_lint(*steps, workers=4, env=env)

    def test_lint_steps_before_an_install_run_together_and_the_later_ones_wait_for_it(self):
        rc, lines, out = self.install_steps(self.INSTALL, self.L3_CHECKS)
        self.assertEqual(list(by_step(lines).items()),
                         [("l1", "PASS"), ("l2", "PASS"), ("Install deps", "PASS"), ("l3", "PASS")], out)
        self.assertEqual(rc, 0, out)
        # Order of the start lines: the install CI step starts before the lint CI step after it. A build with no barrier
        # starts that lint step as soon as the run begins, before the install CI step starts.
        order = [ln for ln in self.err_lines if ln in ("start: Install deps", "start: l3")]
        self.assertEqual(order, ["start: Install deps", "start: l3"],
                         "the lint CI step after the install started before the install:\n" + out)

    def test_a_failed_install_leaves_the_later_lint_steps_unknown_and_the_earlier_ones_pass(self):
        rc, lines, out = self.install_steps('echo "npm: stub install failed" >&2\nexit 1',
                                            "rv.arrive('l3-ran')\nprint('l3 ran')\n")
        self.assertEqual(list(by_step(lines).items()),
                         [("l1", "PASS"), ("l2", "PASS"), ("Install deps", "unknown"), ("l3", "unknown")], out)
        self.assertEqual(rc, 2, out)
        self.assertFalse(os.path.exists(os.path.join(self.root, "l3-ran")), "a lint step ran after its install failed:\n" + out)

    # Controls: each stays serial, and each passes on the serial code it already has.

    def test_workers_one_keeps_the_serial_lines_and_the_serial_start_order(self):
        err_path = os.path.join(self.root, "stderr.txt")
        seen = ("err = open(os.environ['ERR_FILE'], encoding='utf-8').read()\n"
                "open('seen-one.txt', 'w').write('one:%s two:%s' % ('start: one' in err, 'start: two' in err))\n")
        steps = (self.lint("one", seen + "print('one')\n"), self.lint("two", "print('two')\nsys.exit(1)\n"),
                 self.lint("three", "print('three')\n"))
        argv, env = self.job_call(*steps, args=("--lint", "--base", "origin/main"),
                                  env={"CI_JOB_LINT_WORKERS": "1", "ERR_FILE": err_path})
        with open(err_path, "w", encoding="utf-8") as err:
            proc = subprocess.run(argv, cwd=self.root, stdout=subprocess.PIPE, stderr=err, text=True, env=env)
        self.assertEqual(normal(proc.stdout.splitlines()),
                         ["PASS one: PASS SHELL (N)", "FAIL two: FAIL SHELL rc=1 (N) log=L",
                          "PASS three: PASS SHELL (N)", "summary: ran 3 of 3 steps", "log=L"], proc.stdout)
        self.assertEqual(self.read("seen-one.txt"), "one:True two:False", "the second step's start line was out before the first ran")
        self.assertEqual(proc.returncode, 1, proc.stdout)

    def serial_probe(self, args):
        """Runs two steps, the first a probe. The probe writes whether the second step's start line was already on stderr
        when it began: a serial run has not started the second step yet. Returns (stdout lines, rc, the probe's answer)."""
        err_path = os.path.join(self.root, "stderr.txt")
        probe = ("err = open(os.environ['ERR_FILE'], encoding='utf-8').read()\n"
                 "open('seen-b.txt', 'w').write(str('start: b' in err))\n")
        steps = (self.lint("a", probe + "print('a')\n"), self.lint("b", "print('b')\n"))
        argv, env = self.job_call(*steps, args=args, env={"CI_JOB_LINT_WORKERS": "4", "ERR_FILE": err_path})
        with open(err_path, "w", encoding="utf-8") as err:
            proc = subprocess.run(argv, cwd=self.root, stdout=subprocess.PIPE, stderr=err, text=True, env=env)
        return proc.stdout.splitlines(), proc.returncode, self.read("seen-b.txt"), proc.stdout

    def test_a_run_without_lint_keeps_its_steps_serial(self):
        lines, rc, seen, out = self.serial_probe(args=())
        self.assertEqual((list(by_step(lines).items()), seen), ([("a", "PASS"), ("b", "PASS")], "False"), out)
        self.assertEqual(rc, 0, out)

    def test_a_step_run_keeps_its_steps_serial(self):
        lines, rc, seen, out = self.serial_probe(args=("--step", "a", "--step", "b"))
        self.assertEqual((list(by_step(lines).items()), seen), ([("a", "PASS"), ("b", "PASS")], "False"), out)
        self.assertEqual(rc, 0, out)

    def test_plan_under_lint_runs_nothing_and_lists_the_steps_in_order(self):
        steps = self.rendezvous_steps(["a", "b"]) + [self.lint("c", "print('c')\n")]
        code, lines, out = plan_lint(self.root, workflow(*steps))
        self.assertEqual((code, selected(lines)), (0, ["a", "b", "c"]), out)
        self.assertEqual([n for n in os.listdir(self.root) if n.startswith(("arrived", "done", "printed"))], [], out)

    def test_with_no_cpu_count_the_steps_still_run(self):
        rc, lines, out = self.run_lint(self.lint("x1", "print('x1')\n"), self.lint("x2", "print('x2')\n"),
                                       self.lint("x3", "print('x3')\n"), launch=cpus(None))
        self.assertEqual(list(by_step(lines).items()), [("x1", "PASS"), ("x2", "PASS"), ("x3", "PASS")], out)
        self.assertEqual(rc, 0, out)


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
        # CI's checkout has actions/code-check, the table it reads from lint/, and the root ruff.toml that sets its ruff
        # rules. A local uses: runs the repo under test's own copy. The base carries all three (lane commits them), so
        # the diff under test has none of them.
        shutil.copytree(os.path.join(CHECKOUT, "actions", "code-check"),
                        os.path.join(self.root, "actions", "code-check"))
        shutil.copytree(os.path.join(CHECKOUT, "actions", "zizmor"), os.path.join(self.root, "actions", "zizmor"))
        os.makedirs(os.path.join(self.root, "lint"))
        shutil.copyfile(os.path.join(CHECKOUT, "lint", "code_check_standard.json"),
                        os.path.join(self.root, "lint", "code_check_standard.json"))
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
    code_check_standard.json. pipx caches the tool, so only a first run downloads it. A probe over 60 s counts as no."""
    if not shutil.which("pipx"):
        return False
    with open(os.path.join(CHECKOUT, "lint", "code_check_standard.json"), encoding="utf-8") as f:
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
        """A copied install: ci-job, verdict and ste-changed as plain files, hooks/ and lint/ beside them, and a global rules
        file whose @-line names claude_md_checkout. Returns the copied ci-job and the config dir."""
        cfg = os.path.join(self.root, "cfg")
        os.makedirs(os.path.join(cfg, "bin"))
        for name in ("ci-job", "verdict", "ste-changed"):
            shutil.copy2(os.path.join(HERE, "..", "bin", name), os.path.join(cfg, "bin", name))  # copy2: ste-changed runs as a program
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


def pipx_stub_env():
    """PATH with a stub pipx first, which exits 0. A zizmor step reads a missing pipx as unknown, so the stub keeps the
    run.sh under test the only reason in play."""
    bin_dir = tempfile.mkdtemp(prefix="pipx-", dir=RUN_FOLDER)
    stub = os.path.join(bin_dir, "pipx")
    with open(stub, "w", encoding="utf-8", newline="\n") as f:
        f.write("#!/bin/sh\nexit 0\n")
    os.chmod(stub, 0o755)
    return {"PATH": os.pathsep.join([bin_dir, os.environ.get("PATH", "")])}


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
        """PATH with a stub pipx first (pipx_stub_env), so the missing run.sh is the only reason in play."""
        return pipx_stub_env()

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


HARNESS = '''import os, sys
# Stands in for actions/code-check/code_check.py: its verdict is the rule that the tree's lint/rule.txt names.
root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
with open(os.path.join(root, "lint", "rule.txt"), encoding="utf-8") as f:
    rule = f.read().strip()
print("fixture harness: " + rule)
sys.exit(0 if rule == "lenient" else 1)
'''
UNFETCHABLE = "3c5a9e0b7d1f4824a6e9c0d5b7f1a2e4c8d6b9f0"  # 40 hex, in no clone of the fixture
ZIZMOR_LENIENT = "echo 'fixture zizmor: lenient'\nexit 0\n"  # stands in for actions/zizmor/run.sh, which runs pipx
ZIZMOR_STRICT = "echo 'fixture zizmor: strict'\nexit 1\n"


def git_in(repo, *args):
    """One git call in `repo`, its output stripped. LintTools.git drives only the throwaway repo, so the source repo uses this."""
    return subprocess.run(["git", "-C", repo, *args], check=True, env=ENV, capture_output=True, text=True).stdout.strip()


def write_lf(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


class PinnedHarness(Job):
    """A remote claude-settings uses: pinned to a 40-hex sha runs that action's harness from a tree exported at that sha,
    never the local copy (R67: no flag). The source repo is the pointer checkout: commit A (the lenient rule), commit B (HEAD,
    the strict rule) and commit N (B with no harness). The copied ci-job's local copy holds the strict rule, as a checkout at
    HEAD does. A local uses: runs the repo's own copy. The zizmor run.sh follows the same pattern: A and B hold one, N holds
    none. A pinned tree that holds a symlink still exports where os.symlink is refused."""

    git = LintTools.git  # the throwaway child repo's git, one home (LintTools)
    lane = LintTools.lane
    install = CodeCheckFromCopiedInstall.install  # the copied install: this class calls it, it does not copy it
    pipx_env = ZizmorBranches.pipx_env  # the stub pipx the zizmor branch needs: one home (ZizmorBranches)
    LINT = ("--step", "Code check", "--base", "origin/main")

    def setUp(self):
        super().setUp()
        self.lane({"a.py": 'print("fine")\n'})
        self.source = tempfile.mkdtemp(prefix="claude-settings-", dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, self.source, True)
        git_in(self.source, "init", "-q", "-b", "main")
        write_lf(os.path.join(self.source, "actions", "code-check", "code_check.py"), HARNESS)
        write_lf(os.path.join(self.source, "actions", "zizmor", "run.sh"), ZIZMOR_LENIENT)
        write_lf(os.path.join(self.source, "lint", "rule.txt"), "lenient\n")
        git_in(self.source, "add", "-A")
        git_in(self.source, "commit", "-qm", "lenient")
        self.pin_a = git_in(self.source, "rev-parse", "HEAD")
        write_lf(os.path.join(self.source, "lint", "rule.txt"), "strict\n")
        write_lf(os.path.join(self.source, "actions", "zizmor", "run.sh"), ZIZMOR_STRICT)
        git_in(self.source, "commit", "-qam", "strict")
        git_in(self.source, "checkout", "-qb", "no-harness")
        git_in(self.source, "rm", "-q", "actions/code-check/code_check.py", "actions/zizmor/run.sh")
        git_in(self.source, "commit", "-qm", "no harness")
        self.pin_n = git_in(self.source, "rev-parse", "HEAD")
        git_in(self.source, "checkout", "-q", "main")
        self.ci_job, self.cfg = self.install(self.source)
        write_lf(os.path.join(self.cfg, "actions", "code-check", "code_check.py"), HARNESS)  # the local copy: strict
        write_lf(os.path.join(self.cfg, "actions", "zizmor", "run.sh"), ZIZMOR_STRICT)  # the local copy: strict
        write_lf(os.path.join(self.cfg, "lint", "rule.txt"), "strict\n")
        self.assertEqual(git_in(self.source, "show", "%s:lint/rule.txt" % self.pin_a), "lenient")  # the fixture's pin is lenient
        self.logs = tempfile.mkdtemp(prefix="logs-", dir=RUN_FOLDER)  # one log per run, outside the child repo
        self.addCleanup(shutil.rmtree, self.logs, True)

    def run_step(self, steps, *args, env=None, log=None, launch=()):
        """One run of `steps` (step texts) through the copied install, with its own log. -> (rc, verdict lines, output and log)."""
        log = log or self.log
        rc, lines, out = self.run_job(steps, args=args, script=self.ci_job, launch=launch,
                                      env={"CLAUDE_CONFIG_DIR": self.cfg, "VERDICT_LOG": log, **(env or {})})
        text = ""
        if os.path.exists(log):  # no step ran under a usage error, so no log exists then
            with open(log, encoding="utf-8") as f:
                text = f.read()
        return rc, lines, out + text

    def run_pinned(self, ref, *flags, env=None):
        """One run of the step pinned to `ref` (a sha or a branch name). -> (rc, verdict lines, the output and the log)."""
        return self.run_step(self.code_step(ref), *self.LINT, *flags, env=env)

    @staticmethod
    def code_step(ref):
        return step("Code check", uses="shivinate7/claude-settings/actions/code-check@%s" % ref)

    @staticmethod
    def zizmor_step(ref):
        return step(ZIZMOR, uses="shivinate7/claude-settings/actions/zizmor@%s" % ref, **{"with": {"paths": ".github/ actions/"}})

    def add_ste_lint(self):
        """Two commits on the source's main, each holding this checkout's ste-lint files. The first is the pin. The second
        changes lint/ste_lint.py, one of the files CI runs for ste-lint (bin/ste-changed's LINT_FILES). -> the pin's sha.
        The files are copied from this checkout at run time, as CodeCheckFromCopiedInstall copies them: bin/ste-changed
        imports and runs them, and no copy is kept in the repo."""
        for rel in ("bin/ste-changed", "actions/ste-lint", "lint", "hooks"):
            src, dst = os.path.join(CHECKOUT, rel), os.path.join(self.source, rel)
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "test_*"))
            else:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)  # copy2 keeps the mode: the pinned tree runs bin/ste-changed as a program
        git_in(self.source, "add", "-A")
        git_in(self.source, "commit", "-qm", "ste-lint files")
        pin = git_in(self.source, "rev-parse", "HEAD")
        with open(os.path.join(self.source, "lint", "ste_lint.py"), "a", encoding="utf-8", newline="\n") as f:
            f.write("\n# a line the pinned copy does not have\n")
        git_in(self.source, "commit", "-qam", "change ste_lint.py")
        return pin

    def symlink_pin(self):
        """A commit on the lenient harness that holds AGENTS.md as a symlink to CLAUDE.md, as the real repo does. git makes
        the symlink as an index entry, so no filesystem symlink is created: the fixture builds where symlinks are refused too.
        -> the pin's sha."""
        git_in(self.source, "checkout", "-qb", "symlinked", self.pin_a)
        write_lf(os.path.join(self.source, "CLAUDE.md"), "rules\n")
        git_in(self.source, "add", "CLAUDE.md")
        blob = subprocess.run(["git", "-C", self.source, "hash-object", "-w", "--stdin"], input="CLAUDE.md", check=True,
                              env=ENV, capture_output=True, text=True).stdout.strip()
        git_in(self.source, "update-index", "--add", "--cacheinfo", "120000,%s,AGENTS.md" % blob)
        git_in(self.source, "commit", "-qm", "AGENTS.md is a symlink to CLAUDE.md")
        sha = git_in(self.source, "rev-parse", "HEAD")
        self.assertEqual(git_in(self.source, "ls-tree", sha, "AGENTS.md").split()[0], "120000",
                         "precondition: the pinned commit does not hold AGENTS.md as a symlink")
        return sha

    def pin_child(self, action, sha):
        """The child's checks workflow pins `action` at `sha`. bin/ste-changed reads each pin from the linted repo's workflows."""
        write_lf(os.path.join(self.root, ".github", "workflows", "checks.yml"),
                 "jobs:\n  checks:\n    steps:\n      - uses: shivinate7/claude-settings/actions/%s@%s\n" % (action, sha))

    def write_child_code_check(self):
        """The child repo's own code-check action, which a local uses: runs in place."""
        write_lf(os.path.join(self.root, "actions", "code-check", "code_check.py"), "print('child harness')\n")

    @staticmethod
    def git_stub(root):
        """A stub git first on PATH that logs each `git archive` and `git fetch` call, then runs the real git. A line for an
        archive is `archive <n>`: n is how many export folders the run's TMPDIR held when the archive ran. -> (the env that
        puts the stub first, the path of its call log). A shell script, so posix only."""
        bin_dir = tempfile.mkdtemp(prefix="gitstub-", dir=root)
        calls = os.path.join(bin_dir, "calls.txt")
        script = ('#!/bin/sh\n'
                  'case "$1" in\n'
                  '  archive) echo "archive $(ls "${TMPDIR:-/tmp}" | grep -c \'^ci-job-pin-\')" >> "%s" ;;\n'
                  '  fetch) echo "fetch" >> "%s" ;;\n'
                  'esac\n'
                  'exec "%s" "$@"\n') % (calls, calls, shutil.which("git"))
        with open(os.path.join(bin_dir, "git"), "w", encoding="utf-8", newline="\n") as f:
            f.write(script)
        os.chmod(os.path.join(bin_dir, "git"), 0o755)
        return {"PATH": os.pathsep.join([bin_dir, os.environ.get("PATH", "")])}, calls

    @staticmethod
    def stub_calls(calls, kind=""):
        """The lines the git stub logged that start with `kind` ("archive" or "fetch"; "" for every line). [] when none."""
        if not os.path.exists(calls):
            return []
        with open(calls, encoding="utf-8") as f:
            return [ln for ln in f.read().splitlines() if ln.startswith(kind)]

    def test_a_pinned_sha_runs_the_harness_at_that_commit(self):  # R67: no pin flag, a sha pin runs its own harness
        rc, lines, text = self.run_pinned(self.pin_a)
        self.assertEqual((rc, self.verdicts(lines)), (0, ["PASS"]), "the step at a sha pin did not PASS\n" + text)
        self.assertIn("fixture harness: lenient", text, "the local strict copy ran, not the harness at the pin\n" + text)

    def test_a_sha_no_clone_holds_reads_unknown_and_the_local_copy_never_runs(self):
        rc, lines, text = self.run_pinned(UNFETCHABLE)
        self.assertEqual((rc, self.verdicts(lines)), (2, ["unknown"]), "an unfetchable pin did not read unknown\n" + text)
        self.assertIn("pin", lines[0], "the unknown line does not name the pin\n" + text)
        self.assertIn("git fetch origin %s" % UNFETCHABLE, lines[0], "the unknown line does not name the fetch that failed\n" + text)
        self.assertNotIn("fixture harness", text, "the local copy ran for a sha it could not fetch\n" + text)

    def test_a_tree_at_the_pin_without_the_harness_reads_unknown(self):
        rc, lines, text = self.run_pinned(self.pin_n)
        self.assertEqual((rc, self.verdicts(lines)), (2, ["unknown"]), "a pin whose tree lacks the harness did not read unknown\n" + text)
        self.assertIn("code_check.py", lines[0], "the unknown line does not name the harness it could not find\n" + text)
        self.assertNotIn("fixture harness", text, "the local copy ran for a pin whose tree lacks the harness\n" + text)

    def test_a_pinned_tree_with_a_symlink_still_runs_where_symlinks_are_refused(self):
        """A pin whose tree holds a symlink exports, and its harness runs, where os.symlink is refused: the harness does not
        need the symlink member."""
        pin = self.symlink_pin()
        rc, lines, text = self.run_step(self.code_step(pin), *self.LINT, launch=("-c", REFUSE_SYMLINKS))
        self.assertNotIn("git archive of", "\n".join(lines), "the export of a pin with a symlink failed where symlinks are refused\n" + text)
        self.assertEqual((rc, self.verdicts(lines)), (0, ["PASS"]), "the pinned code-check did not PASS where symlinks are refused\n" + text)
        self.assertIn("fixture harness: lenient", text, "the harness at the pin did not run where symlinks are refused\n" + text)

    def test_a_pinned_tree_with_a_symlink_runs_where_symlinks_work(self):
        """Control: the same pin with symlinks allowed passes, so the fixture alone is no failure."""
        pin = self.symlink_pin()
        rc, lines, text = self.run_pinned(pin)
        self.assertEqual((rc, self.verdicts(lines)), (0, ["PASS"]), "the pinned code-check with a symlink in its tree did not PASS\n" + text)
        self.assertIn("fixture harness: lenient", text, "the harness at the pin did not run with a symlink in its tree\n" + text)

    def test_a_stale_ste_lint_pin_runs_its_own_ste_lint_and_reads_the_pin_unknown(self):  # R67: the pinned tree has no .git
        pin = self.add_ste_lint()
        self.pin_child("ste-lint", pin)
        ste = step("STE lint", uses="shivinate7/claude-settings/actions/ste-lint@%s" % pin)
        rc, lines, text = self.run_step(ste, "--step", "STE lint", "--base", "origin/main")
        note = [ln for ln in text.splitlines() if ln.startswith("ste-changed: CI pins ste-lint at %s" % pin[:7])]
        self.assertEqual(len(note), 1, "scope: no line names the stale pin\n" + text)
        self.assertIn("Unknown whether it matches", note[0], "the pinned tree read its pin as drift, not unknown\n" + text)
        self.assertEqual((rc, self.verdicts(lines)), (0, ["PASS"]), "the pinned ste-lint did not PASS\n" + text)

    def test_a_zizmor_pin_runs_its_own_run_sh_and_not_the_local_copy(self):
        rc, lines, text = self.run_step(self.zizmor_step(self.pin_a), "--step", ZIZMOR, env=self.pipx_env())  # R67: no flag
        self.assertEqual((rc, self.verdicts(lines)), (0, ["PASS"]), "the pinned zizmor step did not PASS\n" + text)
        self.assertIn("fixture zizmor: lenient", text, "the local strict run.sh ran, not the one at the pin\n" + text)

    def test_a_pinned_tree_with_no_zizmor_run_sh_reads_unknown_and_names_the_file(self):
        rc, lines, text = self.run_step(self.zizmor_step(self.pin_n), "--step", ZIZMOR, env=self.pipx_env())
        self.assertEqual((rc, self.verdicts(lines)), (2, ["unknown"]), "a pin whose tree has no zizmor run.sh did not read unknown\n" + text)
        self.assertIn("actions/zizmor/run.sh", lines[0], "the unknown line does not name the file it could not find\n" + text)
        self.assertNotIn("fixture zizmor", text, "the local copy ran for a pin whose tree has no run.sh\n" + text)

    def test_a_sha_the_clone_lacks_is_fetched_from_its_origin_and_its_harness_runs(self):
        home = tempfile.mkdtemp(prefix="origin-", dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, home, True)
        bare, work = os.path.join(home, "origin.git"), os.path.join(home, "work")
        subprocess.run(["git", "init", "-q", "--bare", bare], check=True, env=ENV)
        subprocess.run(["git", "init", "-q", "-b", "main", work], check=True, env=ENV)
        write_lf(os.path.join(work, "actions", "code-check", "code_check.py"), HARNESS)
        write_lf(os.path.join(work, "lint", "rule.txt"), "lenient\n")
        git_in(work, "add", "-A")
        git_in(work, "commit", "-qm", "held by origin only")
        sha = git_in(work, "rev-parse", "HEAD")
        git_in(work, "push", bare, "HEAD:refs/heads/fixed")
        git_in(self.source, "remote", "add", "origin", bare)
        held = subprocess.run(["git", "-C", self.source, "cat-file", "-e", sha + "^{commit}"], env=ENV, capture_output=True)
        self.assertNotEqual(held.returncode, 0, "precondition: the clone already holds the sha, so no fetch is tested")
        rc, lines, text = self.run_pinned(sha)
        self.assertEqual((rc, self.verdicts(lines)), (0, ["PASS"]), "a sha the clone lacks was not fetched from its origin and run\n" + text)
        self.assertIn("fixture harness: lenient", text, "the harness run was not the one at the fetched sha\n" + text)

    def test_lint_runs_the_pinned_harness_not_the_local_copy(self):  # R67: --lint follows the pin with no flag
        rc, lines, text = self.run_step(self.code_step(self.pin_a), "--lint", "--base", "origin/main")
        self.assertIn("Code check", by_step(lines), "scope: --lint did not select the code-check step\n" + text)
        self.assertIn("fixture harness: lenient", text, "--lint ran the local copy, not the harness at the pin\n" + text)
        self.assertNotIn("fixture harness: strict", text, "--lint ran the local strict copy beside the pinned harness\n" + text)

    def test_plan_with_a_pin_prints_would_run(self):  # R67: a plan follows no pin, so it lists the step and fetches nothing
        rc, lines, text = self.run_step(self.code_step(self.pin_a), "--plan", "--step", "Code check", "--base", "origin/main")
        self.assertEqual(by_step(lines).get("Code check"), "would run", "scope: the plan does not reach the code-check step\n" + text)
        self.assertEqual(rc, 0, "the plan with a pin did not exit 0\n" + text)

    @unittest.skipUnless(os.name == "posix", "the git stub is a shell script")
    def test_plan_with_an_unfetchable_pin_says_would_run_and_never_fetches(self):
        """R67: --plan resolves no pin and fetches nothing, so a sha no clone holds reads unknown and names the fetch a run would
        make first."""
        env, calls = self.git_stub(RUN_FOLDER)
        _, lines, text = self.run_pinned(UNFETCHABLE, "--plan", env=env)
        self.assertIn("Code check", by_step(lines), "scope: the plan does not reach the code-check step\n" + text)
        self.assertEqual(by_step(lines)["Code check"], "unknown", "an unfetchable pin under --plan did not read unknown\n" + text)
        self.assertTrue(any("--plan does not fetch" in ln for ln in lines), "the unknown line does not say --plan does not fetch\n" + text)
        self.assertEqual(self.stub_calls(calls), [], "under --plan git fetched or archived the pin\n" + text)

    def assert_local_uses_runs_the_repo_copy(self, uses):
        """A local uses: runs the repo under test's own code_check.py, never a pinned tree (R67: no flag)."""
        self.write_child_code_check()
        rc, lines, text = self.run_step(step("Code check", uses=uses), *self.LINT)
        self.assertIn("child harness", text, "scope: the local uses did not run the repo's own copy\n" + text)
        self.assertNotIn("fixture harness", text, "a local uses: ran a harness from a pinned tree or the local copy\n" + text)

    def test_a_local_dollar_uses_runs_the_repos_own_copy(self):
        self.assert_local_uses_runs_the_repo_copy("$/actions/code-check")

    def test_a_local_dot_uses_runs_the_repos_own_copy(self):
        self.assert_local_uses_runs_the_repo_copy("./actions/code-check")

    @unittest.skipUnless(os.name == "posix", "the git stub is a shell script")
    def test_the_export_is_deleted_after_a_pass_and_after_an_unknown(self):
        tmp = tempfile.mkdtemp(prefix="tmp-", dir=RUN_FOLDER)  # TMPDIR for the run: each export is made here
        self.addCleanup(shutil.rmtree, tmp, True)
        env, calls = self.git_stub(RUN_FOLDER)
        env["TMPDIR"] = tmp
        rc, lines, text = self.run_step(self.code_step(self.pin_a), *self.LINT, env=env)
        self.assertEqual((rc, self.verdicts(lines)), (0, ["PASS"]), "precondition: the pinned pass did not run\n" + text)
        self.assertEqual(self.stub_calls(calls, "archive"), ["archive 1"], "precondition: the pass did not export into TMPDIR\n" + text)
        self.assertEqual([n for n in os.listdir(tmp) if n.startswith("ci-job-pin-")], [], "an export was left behind after a pass\n" + text)
        rc, lines, text = self.run_step(self.code_step(self.pin_n), *self.LINT, env=env)
        self.assertEqual(self.verdicts(lines), ["unknown"], "precondition: the pin with no harness did not read unknown\n" + text)
        self.assertEqual(self.stub_calls(calls, "archive"), ["archive 1", "archive 1"], "precondition: the unknown did not export into TMPDIR\n" + text)
        self.assertEqual([n for n in os.listdir(tmp) if n.startswith("ci-job-pin-")], [], "an export was left behind after an unknown\n" + text)

    @unittest.skipUnless(os.name == "posix", "the git stub is a shell script")
    def test_two_steps_pinned_at_one_sha_export_it_once(self):
        env, calls = self.git_stub(RUN_FOLDER)
        steps = step("Code check", uses="shivinate7/claude-settings/actions/code-check@%s" % self.pin_a) + \
            step("Code check again", uses="shivinate7/claude-settings/actions/code-check@%s" % self.pin_a)
        rc, lines, text = self.run_step(steps, "--step", "Code check", "--step", "Code check again", "--base", "origin/main",
                                        env=env)
        self.assertEqual((rc, self.verdicts(lines)), (0, ["PASS", "PASS"]), "the two pinned steps did not both PASS\n" + text)
        exports = self.stub_calls(calls, "archive")
        self.assertEqual(len(exports), 1, "two steps at one sha made %d exports, not one\n%s" % (len(exports), text))


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
ZIZMOR_USES = "shivinate7/claude-settings/actions/zizmor@%s"  # a pin of the zizmor action, at a ref
RUN_SH_A = "#!/bin/sh\necho A > zizmor-A.txt\n"  # pin A's zizmor run.sh: writes a file named for its own commit
RUN_SH_B = "#!/bin/sh\necho B > zizmor-B.txt\n"  # pin B's zizmor run.sh
CODE_CHECK_A = "import pathlib\npathlib.Path('code-check-A.txt').write_text('A\\n')\n"  # pin A's code_check.py
CODE_CHECK_B = "import pathlib\npathlib.Path('code-check-B.txt').write_text('B\\n')\n"  # pin B's code_check.py
CODE_CHECK_FAIL_A = "import pathlib, sys\npathlib.Path('code-check-A.txt').write_text('A\\n')\nsys.exit(1)\n"  # pin A's, failing
RUN_SH_SEEN_B = '#!/bin/sh\necho B > zizmor-B.txt\nprintf "%s" "$CLAUDE_SETTINGS_DIR" > seen-B.txt\n'  # pin B's run.sh: reports its settings dir
LOCAL_CODE_CHECK = ("import os, pathlib, sys\n"
                    "pathlib.Path('local-code-check.txt').write_text(os.environ.get('CLAUDE_SETTINGS_DIR', '(unset)') + '\\n')\n"
                    "sys.exit(%d)\n")  # the repo under test's own code_check.py: its side file records the settings dir it got
LOCAL_RUN_SH = "printf '%s' \"$CLAUDE_SETTINGS_DIR\" > local-zizmor.txt\n"  # the repo under test's own run.sh: its side file records the settings dir
READ_PINNED = 'test "$(cat "$CLAUDE_SETTINGS_DIR/marker")" = pinned'
READ_LOCAL = 'test "$(cat "$CLAUDE_SETTINGS_DIR/marker")" = local'
ABSENT_SHA = "deadbeef" * 5  # forty hex digits that neither the fixture clone nor its origin holds
CODE_CHECK_STUB = "import pathlib\npathlib.Path('pinned-code-check.txt').write_text('pinned\\n')\n"
STE_CHANGED_STUB = "#!/bin/sh\necho pinned > ste-pinned.txt\n"
STE_CHANGED_A = "#!/bin/sh\necho A > ste-A.txt\n"  # pin A's bin/ste-changed: writes a file named for its own commit
STE_CHANGED_B = "#!/bin/sh\necho B > ste-B.txt\n"  # pin B's bin/ste-changed, over the copy B inherits from A
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
    its lint steps; its plan reads no pin, so it lists the steps and fetches nothing. A local uses: step (`$/actions/...`,
    `./actions/...`) takes no pin: its code check and zizmor run the repo under test's own file, and its ste lint runs
    ci-job's own bin/ste-changed, so two pins do not make it unknown."""

    def setUp(self):
        super().setUp()
        self.fixture = tempfile.mkdtemp(prefix="pinned_", dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, self.fixture, True)
        self.decoy = os.path.join(self.fixture, "decoy")
        os.makedirs(self.decoy)
        with open(os.path.join(self.decoy, "marker"), "w", encoding="utf-8", newline="\n") as f:
            f.write("local\n")

    def settings(self, *, fetch_only=False, extra=None, executable=(), local_extra=None):
        """Build the fixture clone. Without fetch_only the clone is cloned from origin and holds A; with it the clone has
        its own history, so A is absent until ci-job fetches it. `extra` adds files to A, `local_extra` to the clone's
        own commit B. Scope first (P7): each marker reads what the case needs."""
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
        self.sha_b = fixture_commit(self.clone, {"marker": "local\n", **(local_extra or {})}, "local", executable)
        self.assertEqual(fixture_git(origin, "show", self.sha_a + ":marker"), "pinned")
        self.assertEqual(fixture_git(self.clone, "show", "HEAD:marker"), "local")
        absent = fixture_rc(self.clone, "cat-file", "-e", self.sha_a + "^{commit}") != 0
        self.assertEqual(absent, fetch_only, "the clone holds pin A" if fetch_only else "the clone lacks pin A")
        return self.clone

    def pinned_env(self, clone=None, extra=None):
        """The env of one ci-job run: the decoy and the clone seam are the only settings values, and the run's temp
        folder is under this run's folder, so a pinned tree a run leaves is swept with the fixture. `extra` is added last."""
        tmp = os.path.join(self.fixture, "tmp")
        os.makedirs(tmp, exist_ok=True)
        env = {k: v for k, v in ENV.items() if k not in ("CLAUDE_SETTINGS_DIR", "CI_JOB_SETTINGS_CLONE", "TMPDIR")}
        env.update(CLAUDE_SETTINGS_DIR=self.decoy, CI_JOB_SETTINGS_CLONE=self.clone if clone is None else clone,
                   TMPDIR=tmp, VERDICT_LOG=self.log, **(extra or {}))
        return env

    def wf_argv(self, text, job, args=()):
        """argv of one ci-job run of `job` in the workflow `text`, written into this run's throwaway repo."""
        path = os.path.join(self.root, "wf.yml")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        return [sys.executable, CI_JOB, job, "--workflow", path, *args]

    def run_text(self, text, job, args=(), clone=None, env=None):
        done = subprocess.run(self.wf_argv(text, job, args), cwd=self.root, capture_output=True, text=True,
                              env=self.pinned_env(clone, env), timeout=120)
        lines = [ln for ln in done.stdout.splitlines() if not ln.startswith("log=")]
        return done.returncode, lines, done.stdout + done.stderr

    def run_pinned(self, *steps, args=(), clone=None, env=None):
        """One ci-job run of the job: the fixture clone is the pin's source, and the decoy is the caller's own value."""
        return self.run_text(workflow(*steps), "lane", args, clone, env)

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

    def test_a_pin_on_a_branch_resolves_to_its_commit_and_runs(self):  # R67: a moving ref is fetched and resolved, then run
        self.settings()
        rc, lines, out = self.run_pinned(
            step("pin", uses=PIN_USES % "main"),
            step("read pinned marker", READ_PINNED),
            args=("--step", "read pinned marker"))
        self.assertEqual((rc, by_step(lines).get("read pinned marker")), (0, "PASS"),
                         "a pin on @main did not resolve to origin's commit and run its tree:\n" + out)

    def test_a_pinned_branch_is_archived_from_its_resolved_commit(self):  # R67: resolve, then archive: the step sees an export
        self.settings()
        rc, lines, out = self.run_pinned(
            step("pin", uses=PIN_USES % "main"),
            step("seen", 'printf "%s" "$CLAUDE_SETTINGS_DIR" > seen.txt\n' + READ_PINNED),
            args=("--step", "seen"))
        self.assertEqual((rc, by_step(lines).get("seen")), (0, "PASS"), "the step under a branch pin did not PASS:\n" + out)
        seen = open(os.path.join(self.root, "seen.txt"), encoding="utf-8").read().strip()
        self.assertIn("ci-job-pin-", seen, "the branch pin's tree is not an archived export: " + seen)
        self.assertFalse(os.path.exists(seen), "the export was left on disk after the run: " + seen)

    def test_a_pin_on_a_branch_that_does_not_exist_is_unknown_naming_the_ref(self):  # R67: an unresolvable ref reads unknown
        self.settings()
        rc, lines, out = self.run_pinned(
            step("pin", uses=PIN_USES % "nosuchbranch"),
            step("write", "echo ran > ran.txt"),
            args=("--step", "write"))
        self.assertEqual((rc, by_step(lines).get("write")), (2, "unknown"),
                         "a pin on a branch origin lacks must make the named step unknown, exit 2:\n" + out)
        line = line_of(lines, "write") or ""
        self.assertIn("nosuchbranch", line, "the unknown line does not name the ref: " + line)
        self.assertFalse(os.path.exists(os.path.join(self.root, "ran.txt")), "a step ran under an unresolvable ref pin")

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

    def test_lint_with_a_pin_on_a_branch_resolves_it_and_runs_each_lint_step(self):  # R67: a moving ref resolves, so lint runs
        self.settings()
        rc, lines, out = self.run_pinned(
            step("pin", uses=PIN_ONLY_USES % "main"),
            self.lint_step("one", "touch", TOUCH_SCRIPT, "one.txt"),
            self.lint_step("two", "touch", TOUCH_SCRIPT, "two.txt"),
            args=("--lint",))
        self.assertEqual(sorted(n for n in by_step(lines) if n in ("one", "two")), ["one", "two"],
                         "precondition: --lint did not list both lint steps:\n" + out)
        self.assertEqual((rc, by_step(lines)["one"], by_step(lines)["two"]), (0, "PASS", "PASS"),
                         "a pin on @main did not resolve, so the lint steps did not pass:\n" + out)
        for side in ("one.txt", "two.txt"):
            self.assertTrue(os.path.exists(os.path.join(self.root, side)), "a lint step did not run: " + side)

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
                for rel in ("actions/code-check/code_check.py", "lint/code_check_standard.json")}
        self.settings(extra=code)  # R67: code_check reads lint/code_check_standard.json from the tree root, so the pin needs both
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
    def test_a_remote_zizmor_under_a_pin_runs_the_pinned_run_sh(self):  # coverage: green on the old code
        self.settings(extra={"actions/zizmor/run.sh": RUN_SH_A})
        self.assertIn("zizmor-A.txt", fixture_git(self.clone, "show", self.sha_a + ":actions/zizmor/run.sh"),
                      "precondition: pin A's run.sh is not the stub that writes zizmor-A.txt")
        rc, lines, out = self.run_pinned(step("zizmor", uses=ZIZMOR_USES % self.sha_a), args=("--step", "zizmor"),
                                         env=pipx_stub_env())
        self.assertTrue(os.path.isfile(os.path.join(self.root, "zizmor-A.txt")),
                        "the pinned run.sh did not run: ci-job ran another run.sh for the pinned zizmor\n" + out)
        self.assertEqual(by_step(lines).get("zizmor"), "PASS",
                         "the pinned run.sh ran, but the zizmor step did not PASS:\n" + out)

    def two_pin_settings(self, run_sh_b=RUN_SH_B):
        """The fixture of two pins: pin A is the origin's commit and pin B is the clone's HEAD. Each carries its own
        code_check.py and run.sh, which write a file named for their commit. Scope first (P7): both pins are in the clone,
        and each commit holds its own stubs, before any verdict is read."""
        self.settings(extra={"actions/code-check/code_check.py": CODE_CHECK_A, "actions/zizmor/run.sh": RUN_SH_A},
                      local_extra={"actions/code-check/code_check.py": CODE_CHECK_B, "actions/zizmor/run.sh": run_sh_b})
        self.assertNotEqual(self.sha_a, self.sha_b, "precondition: the two pins are one commit")
        self.assertIn("code-check-A.txt", fixture_git(self.clone, "show", self.sha_a + ":actions/code-check/code_check.py"),
                      "precondition: pin A's code_check.py is not its own stub")
        self.assertIn("code-check-B.txt", fixture_git(self.clone, "show", self.sha_b + ":actions/code-check/code_check.py"),
                      "precondition: pin B's code_check.py is not its own stub")
        self.assertIn("zizmor-B.txt", fixture_git(self.clone, "show", self.sha_b + ":actions/zizmor/run.sh"),
                      "precondition: pin B's run.sh is not its own stub")

    def two_pin_steps(self, *more):
        """A job with two pins, each action at its own sha as CI pins it: the code check at A, zizmor at B. `more` follow."""
        return [step("code check", uses=PIN_USES % self.sha_a), step("zizmor", uses=ZIZMOR_USES % self.sha_b), *more]

    def test_each_pinned_step_runs_in_its_own_pins_tree(self):
        self.two_pin_settings()
        args = ("--base", "origin/main", "--step", "code check", "--step", "zizmor")
        rc, lines, out = self.run_pinned(*self.two_pin_steps(), args=args, env=pipx_stub_env())
        check, zizmor = line_of(lines, "code check") or "", line_of(lines, "zizmor") or ""
        self.assertTrue(os.path.isfile(os.path.join(self.root, "code-check-A.txt")),
                        "the code check did not run pin A's code_check.py: " + check + "\n" + out)
        self.assertFalse(os.path.exists(os.path.join(self.root, "code-check-B.txt")),
                         "the code check ran pin B's code_check.py, not its own pin A's: " + check)
        self.assertTrue(os.path.isfile(os.path.join(self.root, "zizmor-B.txt")),
                        "the zizmor step did not run pin B's run.sh: " + zizmor + "\n" + out)
        self.assertFalse(os.path.exists(os.path.join(self.root, "zizmor-A.txt")),
                         "the zizmor step ran pin A's run.sh, not its own pin B's: " + zizmor)
        self.assertEqual(by_step(lines).get("code check"), "PASS",
                         "the code check under its own pin A did not PASS: " + check + "\n" + out)
        self.assertEqual(by_step(lines).get("zizmor"), "PASS",
                         "the zizmor step under its own pin B did not PASS: " + zizmor + "\n" + out)
        self.assertEqual(rc, 0, "both named steps passed, so the run must exit 0:\n" + out)
        self.assertEqual(self.worktrees(), 1, "a pinned tree was left in the clone after the run:\n" + out)

    def test_a_plain_step_in_a_job_with_two_pins_is_unknown_and_names_both_pins(self):  # coverage: green on the old code
        self.two_pin_settings()
        plain = step("plain", 'test -d "$CLAUDE_SETTINGS_DIR" && echo ran > plain.txt')  # passes if it runs, so only the pins stop it
        rc, lines, out = self.run_pinned(*self.two_pin_steps(plain), args=("--step", "plain"), env=pipx_stub_env())
        line = line_of(lines, "plain") or ""
        self.assertFalse(os.path.exists(os.path.join(self.root, "plain.txt")), "the plain step ran under two pins:\n" + out)
        self.assertEqual((rc, by_step(lines).get("plain")), (2, "unknown"),
                         "a plain step in a job with two pins must be unknown, exit 2:\n" + out)
        self.assertTrue(self.sha_a[:9] in line and self.sha_b[:9] in line,
                        "the unknown line must name both pins, the ambiguity: " + line)

    def test_a_blocked_named_step_does_not_stop_a_good_one_which_still_passes(self):
        self.settings(extra={"actions/code-check/code_check.py": CODE_CHECK_A})
        rc, lines, out = self.run_pinned(
            step("good pin", uses=PIN_USES % self.sha_a),
            step("blocked pin", uses=ZIZMOR_USES % "main"),
            args=("--base", "origin/main", "--step", "good pin", "--step", "blocked pin"))
        self.assertTrue(os.path.isfile(os.path.join(self.root, "code-check-A.txt")),
                        "precondition: the good step's pinned code_check.py did not run:\n" + out)
        self.assertEqual(by_step(lines).get("good pin"), "PASS",
                         "a blocked named step stopped the good one, which runs in its own pinned tree:\n" + out)
        self.assertEqual(by_step(lines).get("blocked pin"), "unknown",
                         "a named step pinned at @main must read unknown, not run:\n" + out)
        self.assertEqual(rc, 2, "one named step is unknown and none failed, so the run must exit 2:\n" + out)

    def test_a_failing_good_named_step_beside_a_blocked_one_exits_one(self):
        self.settings(extra={"actions/code-check/code_check.py": CODE_CHECK_FAIL_A})
        rc, lines, out = self.run_pinned(
            step("good pin", uses=PIN_USES % self.sha_a),
            step("blocked pin", uses=PIN_USES % ABSENT_SHA),
            args=("--base", "origin/main", "--step", "good pin", "--step", "blocked pin"))
        self.assertTrue(os.path.isfile(os.path.join(self.root, "code-check-A.txt")),
                        "precondition: the failing pinned code_check.py did not run:\n" + out)
        self.assertEqual(by_step(lines).get("good pin"), "FAIL",
                         "a blocked named step hid the FAIL of the good one, whose pinned code_check.py exited 1:\n" + out)
        self.assertEqual(by_step(lines).get("blocked pin"), "unknown",
                         "a pin that cannot be fetched must read unknown, not run:\n" + out)
        self.assertEqual(rc, 1, "a FAIL beats unknown, so the run must exit 1:\n" + out)

    def test_under_two_pins_a_pinned_step_sees_the_callers_settings_dir_not_a_tree(self):
        self.two_pin_settings(run_sh_b=RUN_SH_SEEN_B)
        rc, lines, out = self.run_pinned(*self.two_pin_steps(),
                                         args=("--base", "origin/main", "--step", "code check", "--step", "zizmor"),
                                         env=pipx_stub_env())
        seen_file = os.path.join(self.root, "seen-B.txt")
        self.assertTrue(os.path.isfile(seen_file), "precondition: pin B's run.sh did not run:\n" + out)
        with open(seen_file, encoding="utf-8") as f:
            seen = f.read()
        self.assertEqual(seen, self.decoy, "under two pins ci-job changed CLAUDE_SETTINGS_DIR: the pinned step saw %r, "
                         "not the caller's value:\n%s" % (seen, out))

    def test_two_steps_at_one_pin_share_one_pinned_archive(self):  # R67: one pin, one export, and both steps see its tree
        self.settings(extra={"actions/code-check/code_check.py": CODE_CHECK_A, "actions/zizmor/run.sh": RUN_SH_A})

        def seen(name):
            return 'printf "%s" "$CLAUDE_SETTINGS_DIR" > ' + name

        rc, lines, out = self.run_pinned(
            step("code check", uses=PIN_USES % self.sha_a),
            step("zizmor", uses=ZIZMOR_USES % self.sha_a),
            step("seen one", seen("one.txt")),
            step("seen two", seen("two.txt")),
            args=("--base", "origin/main", "--step", "code check", "--step", "zizmor",
                  "--step", "seen one", "--step", "seen two"),
            env=pipx_stub_env())
        dirs = []
        for name in ("one.txt", "two.txt"):
            path = os.path.join(self.root, name)
            self.assertTrue(os.path.isfile(path), "precondition: the step did not record its settings dir:\n" + out)
            with open(path, encoding="utf-8") as f:
                dirs.append(f.read().strip())
        self.assertEqual(dirs[0], dirs[1], "one pin gave two settings dirs while the steps ran:\n" + out)
        self.assertIn("ci-job-pin-", dirs[0], "the settings dir is not a pinned export: " + dirs[0])

    def test_lint_runs_a_remote_ste_lint_and_code_check_each_from_its_own_pins_tree(self):
        self.settings(extra={"bin/ste-changed": STE_CHANGED_A}, executable=("bin/ste-changed",),
                      local_extra={"bin/ste-changed": STE_CHANGED_B, "actions/code-check/code_check.py": CODE_CHECK_B})
        self.assertNotEqual(fixture_rc(self.clone, "cat-file", "-e", self.sha_a + ":actions/code-check/code_check.py"), 0,
                            "precondition: pin A holds a code_check.py, so the code check could run from A")
        self.assertIn("ste-B.txt", fixture_git(self.clone, "show", self.sha_b + ":bin/ste-changed"),
                      "precondition: pin B's bin/ste-changed is not its own stub")
        rc, lines, out = self.run_pinned(
            step("ste lint", uses="shivinate7/claude-settings/actions/ste-lint@%s" % self.sha_a),
            step("code check", uses=PIN_USES % self.sha_b),
            args=("--lint", "--base", "origin/main"))
        self.assertTrue(os.path.isfile(os.path.join(self.root, "ste-A.txt")),
                        "the ste lint did not run pin A's bin/ste-changed:\n" + out)
        self.assertFalse(os.path.exists(os.path.join(self.root, "ste-B.txt")),
                         "the ste lint ran pin B's bin/ste-changed, not its own pin A's:\n" + out)
        self.assertTrue(os.path.isfile(os.path.join(self.root, "code-check-B.txt")),
                        "the code check did not run pin B's code_check.py:\n" + out)
        self.assertEqual((rc, by_step(lines)), (0, {"ste lint": "PASS", "code check": "PASS"}),
                         "both lint steps pass under their own pins, so --lint must exit 0:\n" + out)

    def test_lint_with_a_blocked_pin_beside_a_good_pin_runs_the_good_step_and_exits_two(self):
        self.settings(extra={"actions/code-check/code_check.py": CODE_CHECK_A})
        self.assertNotEqual(fixture_rc(self.clone, "cat-file", "-e", ABSENT_SHA + "^{commit}"), 0,
                            "precondition: the clone holds the blocked sha, so its pin is not blocked")
        self.assertNotEqual(fixture_rc(os.path.join(self.fixture, "origin"), "cat-file", "-e", ABSENT_SHA + "^{commit}"), 0,
                            "precondition: origin holds the blocked sha, so its pin is not blocked")
        rc, lines, out = self.run_pinned(
            step("good pin", uses=PIN_USES % self.sha_a),
            step("blocked pin", uses=PIN_USES % ABSENT_SHA),
            args=("--lint", "--base", "origin/main"))
        self.assertTrue(os.path.isfile(os.path.join(self.root, "code-check-A.txt")),
                        "the good pin's code_check.py did not run:\n" + out)
        self.assertEqual(by_step(lines), {"good pin": "PASS", "blocked pin": "unknown"},
                         "a blocked pin must read unknown and must not stop the good pin's lint step:\n" + out)
        self.assertIn(ABSENT_SHA[:9], line_of(lines, "blocked pin") or "",
                      "the unknown line must name the blocked sha: " + str(line_of(lines, "blocked pin")))
        self.assertEqual(rc, 2, "one lint step is unknown and none failed, so --lint must exit 2:\n" + out)

    def test_lint_does_not_run_an_install_before_a_lint_step_whose_pin_is_blocked(self):
        self.settings(extra={"actions/code-check/code_check.py": CODE_CHECK_A})
        self.assertNotEqual(fixture_rc(self.clone, "cat-file", "-e", ABSENT_SHA + "^{commit}"), 0,
                            "precondition: the clone holds the blocked sha, so its pin is not blocked")
        env = InstallSteps.stub_path(self, npm=InstallSteps.NPM_OK)  # the npm stub: InstallSteps's one home
        rc, lines, out = self.run_pinned(
            step("good pin", uses=PIN_USES % self.sha_a),  # keeps the all-blocked gate from ending the run before the install
            step("install", "npm ci"),
            step("blocked pin", uses=PIN_USES % ABSENT_SHA),
            args=("--lint", "--base", "origin/main"), env=env)
        self.assertEqual(InstallSteps.npm_calls(self), "(no npm call)",
                         "the install ran before a lint step whose pin is blocked:\n" + out)
        self.assertEqual((rc, by_step(lines)), (2, {"good pin": "PASS", "install": "not run", "blocked pin": "unknown"}),
                         "the install has no lint step after it that will run, so it is not run:\n" + out)

    def test_lint_under_two_pins_a_plain_lint_step_reading_the_settings_dir_is_unknown_beside_pinned_actions(self):
        self.two_pin_settings()
        rc, lines, out = self.run_pinned(
            *self.two_pin_steps(self.lint_step("read settings", "read_marker", MARKER_SCRIPT, "local")),
            args=("--lint", "--base", "origin/main"), env=pipx_stub_env())
        self.assertTrue(os.path.isfile(os.path.join(self.root, "code-check-A.txt")),
                        "precondition: the code check under pin A did not run:\n" + out)
        self.assertTrue(os.path.isfile(os.path.join(self.root, "zizmor-B.txt")),
                        "precondition: the zizmor step under pin B did not run:\n" + out)
        self.assertFalse(os.path.exists(os.path.join(self.root, "seen.txt")),
                         "the plain lint step ran under two pins and read the caller's settings dir:\n" + out)
        line = line_of(lines, "read settings") or ""
        self.assertEqual((rc, by_step(lines).get("read settings")), (2, "unknown"),
                         "a plain lint step under two pins must be unknown, exit 2:\n" + out)
        self.assertTrue(self.sha_a[:9] in line and self.sha_b[:9] in line,
                        "the unknown line must name both pins, the ambiguity: " + line)

    def git_shim_env(self):
        """(env, calls): PATH with a git shim first. The shim appends each git call's arguments to `calls`, then runs the
        real git, so a run's fetch or worktree add shows in that file."""
        bin_dir = tempfile.mkdtemp(prefix="gitshim-", dir=RUN_FOLDER)
        calls = os.path.join(bin_dir, "git-calls.txt")
        stub = os.path.join(bin_dir, "git")
        with open(stub, "w", encoding="utf-8", newline="\n") as f:
            f.write("#!/bin/sh\nprintf '%%s\\n' \"$*\" >> '%s'\nexec '%s' \"$@\"\n" % (calls, shutil.which("git")))
        os.chmod(stub, 0o755)
        return {"PATH": os.pathsep.join([bin_dir, os.environ.get("PATH", "")])}, calls

    def test_lint_with_no_base_fetches_and_adds_no_worktree_for_pull_request_pins_it_reads_unknown(self):
        self.settings(fetch_only=True)  # the clone lacks pin A: a run that needed it would fetch it
        env, calls = self.git_shim_env()
        rc, lines, out = self.run_pinned(
            step("code check", uses=PIN_USES % self.sha_a),
            step("ste lint", uses="shivinate7/claude-settings/actions/ste-lint@%s" % self.sha_a),
            args=("--lint",), env=env)
        self.assertIn("no base resolved", out, "precondition: no base was resolved, so the pull-request steps are skipped:\n" + out)
        self.assertTrue(os.path.isfile(calls), "precondition: the git shim was never called:\n" + out)
        self.assertEqual((by_step(lines).get("code check"), by_step(lines).get("ste lint")), ("unknown", "unknown"),
                         "each pull-request lint step must read unknown with no base:\n" + out)
        for name in ("code check", "ste lint"):
            self.assertIn("skipped for want of a base", line_of(lines, name) or "",
                          "the %s line must say it was skipped for want of a base:\n" % name + out)
        with open(calls, encoding="utf-8") as f:
            made = [c for c in f.read().splitlines() if c.startswith(("fetch", "worktree add"))]
        self.assertEqual(made, [], "every lint step was skipped for want of a base, yet the run fetched pin A or made a pinned worktree:\n" + out)

    def local_code_check(self, uses, exit_code):
        """Write the repo under test's own code_check.py, which a local uses: step runs, and return that step. Its run
        leaves local-code-check.txt, and it exits with `exit_code`."""
        path = os.path.join(self.root, "actions", "code-check", "code_check.py")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(LOCAL_CODE_CHECK % exit_code)
        return step("local code check", uses=uses)

    def assert_local_code_check_passes(self, lines, rc, out):
        line = line_of(lines, "local code check") or ""
        self.assertEqual(by_step(lines).get("local code check"), "PASS",
                         "a local code check under pins must run the repo's own code_check.py and PASS, not read unknown:\n"
                         + line + "\n" + out)
        self.assertTrue(os.path.isfile(os.path.join(self.root, "local-code-check.txt")),
                        "the repo's own code_check.py did not run:\n" + out)
        self.assert_names_own_code_check(line)
        self.assertEqual(rc, 0, "every named or lint step passed, so the run must exit 0:\n" + out)

    def assert_names_own_code_check(self, line):
        """The verdict line names the code_check.py it ran: the repo under test's own file, never a pinned tree's."""
        found = re.search(r"\(code_check\.py: (.+)\)$", line)
        self.assertTrue(found, "the verdict line does not name the code_check.py it ran: " + line)
        own = os.path.join(self.root, "actions", "code-check", "code_check.py")
        self.assertEqual(os.path.realpath(found.group(1)), os.path.realpath(own),
                         "the local step ran a code_check.py other than the repo's own: " + line)

    def test_lint_a_local_code_check_under_two_pins_runs_the_repos_own_code_check_py(self):
        self.two_pin_settings()
        local = self.local_code_check("$/actions/code-check", 0)
        rc, lines, out = self.run_pinned(*self.two_pin_steps(local), args=("--lint", "--base", "origin/main"),
                                         env=pipx_stub_env())
        self.assertTrue(os.path.isfile(os.path.join(self.root, "code-check-A.txt")),
                        "precondition: pin A's code check did not run:\n" + out)
        self.assertTrue(os.path.isfile(os.path.join(self.root, "zizmor-B.txt")),
                        "precondition: pin B's zizmor step did not run:\n" + out)
        self.assert_local_code_check_passes(lines, rc, out)

    def test_step_a_local_code_check_under_two_pins_fails_on_its_own_failing_code_check_py_with_no_settings_clone(self):
        self.two_pin_settings()
        local = self.local_code_check("./actions/code-check", 1)
        missing = os.path.join(self.fixture, "no-such-clone")  # a step that needs no pinned tree runs with no clone to read
        rc, lines, out = self.run_pinned(*self.two_pin_steps(local),
                                         args=("--base", "origin/main", "--step", "local code check"), clone=missing)
        line = line_of(lines, "local code check") or ""
        self.assertEqual(by_step(lines).get("local code check"), "FAIL",
                         "a local code check under two pins must FAIL on its own failing code_check.py, not read unknown:\n"
                         + line + "\n" + out)
        self.assertTrue(os.path.isfile(os.path.join(self.root, "local-code-check.txt")),
                        "the step read FAIL, but the repo's own code_check.py left no file:\n" + out)
        self.assert_names_own_code_check(line)
        self.assertEqual(rc, 1, "a FAIL must exit 1:\n" + out)
        for name in ("code-check-A.txt", "code-check-B.txt", "zizmor-A.txt", "zizmor-B.txt"):
            self.assertFalse(os.path.exists(os.path.join(self.root, name)), "a step that was not named ran: " + name)

    def test_lint_a_local_code_check_under_one_pin_runs_the_repos_own_code_check_py(self):  # control: green on the old code
        self.settings(extra={"actions/code-check/code_check.py": CODE_CHECK_A})
        local = self.local_code_check("$/actions/code-check", 0)
        rc, lines, out = self.run_pinned(step("code check", uses=PIN_USES % self.sha_a), local,
                                         args=("--lint", "--base", "origin/main"))
        self.assertTrue(os.path.isfile(os.path.join(self.root, "code-check-A.txt")),
                        "precondition: pin A's code check did not run:\n" + out)
        self.assert_local_code_check_passes(lines, rc, out)

    def test_lint_a_local_code_check_still_runs_and_prints_when_its_only_remote_pin_is_blocked(self):
        self.settings(extra={"actions/code-check/code_check.py": CODE_CHECK_A})
        local = self.local_code_check("$/actions/code-check", 0)
        missing = os.path.join(self.fixture, "no-such-clone")  # the one pin cannot be made, so its step is blocked
        rc, lines, out = self.run_pinned(step("code check", uses=PIN_USES % self.sha_a), local,
                                         args=("--lint", "--base", "origin/main"), clone=missing)
        self.assertEqual(by_step(lines).get("code check"), "unknown", "precondition: the missing clone must refuse the pin:\n" + out)
        self.assertEqual(by_step(lines).get("local code check"), "PASS",
                         "the local code check printed no verdict, so it never ran beside a blocked remote step:\n" + out)
        self.assertTrue(os.path.isfile(os.path.join(self.root, "local-code-check.txt")),
                        "the repo's own code_check.py did not run:\n" + out)
        self.assert_names_own_code_check(line_of(lines, "local code check") or "")
        self.assertEqual(rc, 2, "one step is unknown and none failed, so --lint must exit 2:\n" + out)

    def test_lint_a_local_code_check_never_gets_a_pinned_settings_dir_beside_a_pinned_remote_step(self):
        self.settings(extra={"actions/code-check/code_check.py": CODE_CHECK_A})
        local = self.local_code_check("$/actions/code-check", 0)
        rc, lines, out = self.run_pinned(step("code check", uses=PIN_USES % self.sha_a), local,
                                         args=("--lint", "--base", "origin/main"))
        self.assertTrue(os.path.isfile(os.path.join(self.root, "code-check-A.txt")),
                        "precondition: the pinned remote step did not run, so no pinned tree existed:\n" + out)
        self.assertEqual(by_step(lines).get("local code check"), "PASS", "the local code check did not PASS:\n" + out)
        self.assertEqual(self.root_file("local-code-check.txt"), self.decoy,
                         "the local code check got CLAUDE_SETTINGS_DIR set to a pinned tree, not the caller's value:\n" + out)

    def local_zizmor(self):
        """Write the repo under test's own run.sh, which a local $/actions/zizmor step runs. It leaves local-zizmor.txt, which
        names the settings dir the step got. Returns that step."""
        run_sh = os.path.join(self.root, "actions", "zizmor", "run.sh")
        os.makedirs(os.path.dirname(run_sh), exist_ok=True)
        with open(run_sh, "w", encoding="utf-8", newline="\n") as f:
            f.write(LOCAL_RUN_SH)
        return step("local zizmor", uses="$/actions/zizmor")

    def test_lint_a_local_zizmor_beside_a_pinned_remote_step_runs_its_own_run_sh_and_never_a_pinned_settings_dir(self):
        self.settings(extra={"actions/code-check/code_check.py": CODE_CHECK_A, "actions/zizmor/run.sh": RUN_SH_A})
        self.assertIn("zizmor-A.txt", fixture_git(self.clone, "show", self.sha_a + ":actions/zizmor/run.sh"),
                      "precondition: pin A's run.sh is not the stub that writes zizmor-A.txt")
        local = self.local_zizmor()
        rc, lines, out = self.run_pinned(step("code check", uses=PIN_USES % self.sha_a), local,
                                         args=("--lint", "--base", "origin/main"), env=pipx_stub_env())
        self.assertTrue(os.path.isfile(os.path.join(self.root, "code-check-A.txt")),
                        "precondition: the pinned code check did not run, so no pinned tree existed:\n" + out)
        self.assertTrue(os.path.isfile(os.path.join(self.root, "local-zizmor.txt")),
                        "the local zizmor step did not run the repo's own run.sh:\n" + out)
        self.assertFalse(os.path.exists(os.path.join(self.root, "zizmor-A.txt")),
                         "the local zizmor step ran pin A's run.sh, not the repo's own:\n" + out)
        self.assertEqual(self.root_file("local-zizmor.txt"), self.decoy,
                         "the local zizmor step got CLAUDE_SETTINGS_DIR other than the caller's value:\n" + out)
        self.assertEqual(by_step(lines).get("local zizmor"), "PASS", "the local zizmor step did not PASS:\n" + out)
        self.assertEqual(rc, 0, "both lint steps pass, so --lint must exit 0:\n" + out)

    def test_step_a_local_code_check_alone_keeps_the_callers_settings_dir_beside_one_pin(self):  # control: no tree under --step
        self.settings(extra={"actions/code-check/code_check.py": CODE_CHECK_A})
        local = self.local_code_check("./actions/code-check", 0)
        rc, lines, out = self.run_pinned(step("code check", uses=PIN_USES % self.sha_a), local,
                                         args=("--base", "origin/main", "--step", "local code check"))
        self.assertFalse(os.path.exists(os.path.join(self.root, "code-check-A.txt")),
                         "precondition: the unnamed pinned step ran:\n" + out)
        self.assertEqual(by_step(lines).get("local code check"), "PASS", "the local code check did not PASS:\n" + out)
        self.assertEqual(self.root_file("local-code-check.txt"), self.decoy,
                         "--step on the local step alone changed CLAUDE_SETTINGS_DIR from the caller's value:\n" + out)

    def quoted_local_code_check_is_the_local_action(self, uses):
        """A step whose `uses:` is quoted is the repo's own code_check.py: it runs there, and its failure is a FAIL."""
        self.settings()
        local = self.local_code_check(uses, 1)
        rc, lines, out = self.run_pinned(local, args=("--lint", "--base", "origin/main"))
        line = line_of(lines, "local code check") or ""
        self.assertEqual(by_step(lines).get("local code check"), "FAIL",
                         "a quoted local uses: is not read as the local action, so its code check did not run:\n" + line + "\n" + out)
        self.assertTrue(os.path.isfile(os.path.join(self.root, "local-code-check.txt")),
                        "the repo's own code_check.py did not run:\n" + out)
        self.assert_names_own_code_check(line)
        self.assertEqual(rc, 1, "a FAIL must exit 1:\n" + out)

    def test_lint_a_single_quoted_local_uses_runs_the_repos_own_code_check_py(self):
        self.quoted_local_code_check_is_the_local_action("'./actions/code-check'")

    def test_lint_a_double_quoted_local_uses_runs_the_repos_own_code_check_py(self):
        self.quoted_local_code_check_is_the_local_action('"$/actions/code-check"')

    branch_with = SteAction.branch_with  # the base and the lane that ste-changed lints: one home, in SteAction

    def test_lint_a_local_ste_lint_runs_the_real_ste_check_under_two_pins_with_no_clone(self):
        self.two_pin_settings()
        self.branch_with(" ".join(["word"] * 40) + " end.")  # an over-long sentence: only the real ste check fails it
        missing = os.path.join(self.fixture, "no-such-clone")  # no pinned tree can be made, and the local step needs none
        rc, lines, out = self.run_pinned(*self.two_pin_steps(step("local ste lint", uses="$/actions/ste-lint")),
                                         args=("--lint", "--base", "origin/main"), clone=missing, env=pipx_stub_env())
        self.assertEqual(by_step(lines).get("code check"), "unknown",
                         "precondition: the missing clone must refuse the pinned steps:\n" + out)
        self.assertEqual(by_step(lines).get("local ste lint"), "FAIL",
                         "the local ste lint did not run ci-job's ste check under two pins with no clone:\n" + out)
        self.assertEqual(rc, 1, "a FAIL outranks the unknown pinned steps, so --lint must exit 1:\n" + out)

    def test_lint_a_local_zizmor_runs_the_repos_own_run_sh_under_two_pins_with_no_clone(self):
        self.two_pin_settings()
        local = self.local_zizmor()
        missing = os.path.join(self.fixture, "no-such-clone")  # no pinned tree can be made, and the local step needs none
        rc, lines, out = self.run_pinned(*self.two_pin_steps(local),
                                         args=("--lint", "--base", "origin/main"), clone=missing, env=pipx_stub_env())
        self.assertEqual(by_step(lines).get("code check"), "unknown",
                         "precondition: the missing clone must refuse the pinned steps:\n" + out)
        self.assertEqual(by_step(lines).get("local zizmor"), "PASS",
                         "the local zizmor step did not PASS on its own run.sh beside two pins:\n" + out)
        self.assertTrue(os.path.isfile(os.path.join(self.root, "local-zizmor.txt")),
                        "the repo's own run.sh left no side file:\n" + out)
        self.assertEqual(self.root_file("local-zizmor.txt"), self.decoy,
                         "the repo's own run.sh got CLAUDE_SETTINGS_DIR other than the caller's value:\n" + out)
        self.assertEqual(rc, 2, "the pinned steps are unknown and none failed, so --lint must exit 2:\n" + out)


if __name__ == "__main__":
    try:
        unittest.main()
    finally:
        shutil.rmtree(RUN_FOLDER, ignore_errors=True)
