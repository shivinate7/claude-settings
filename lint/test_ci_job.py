#!/usr/bin/env python3
"""Fixture suite for bin/ci-job: each case writes a workflow into a throwaway repo and runs one job.

Red cases: a multi-line step whose last line fails, a missing tool (named, behind xargs, or exit 127),
a `uses:` step, an `if:` or env expression the runner cannot read, and a pull-request step with no base.
None of them may read PASS. The last class plans the real checks job: every step gets one line.
Run: python3 lint/test_ci_job.py
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CI_JOB = os.path.join(HERE, "..", "bin", "ci-job")
CHECKS = os.path.join(HERE, "..", ".github", "workflows", "checks.yml")
ENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull, GIT_AUTHOR_NAME="t",
           GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
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
        self.root = tempfile.mkdtemp(prefix="cijob_")
        self.addCleanup(shutil.rmtree, self.root, True)
        subprocess.run(["git", "init", "-q", "-b", "main", self.root], check=True, env=ENV)
        self.log = os.path.join(self.root, "verdict.log")

    def run_job(self, *steps, args=()):
        path = os.path.join(self.root, "wf.yml")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(workflow(*steps))
        env = dict(ENV, VERDICT_LOG=self.log, **{k: v for k, v in os.environ.items() if k == "VERDICT_HEARTBEAT"})
        done = subprocess.run([sys.executable, CI_JOB, "lane", "--workflow", path, *args], cwd=self.root,
                              capture_output=True, text=True, env=env, timeout=120)
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

    def test_with_no_base_the_ste_step_is_skipped_not_passed(self):
        self.branch_with("A short sentence.")
        rc, lines, out = self.run_job(step("STE lint", uses="$/actions/ste-lint"), args=("--lint",))
        self.assertEqual(self.verdicts(lines), ["skipped"], out)

    def test_another_action_is_still_not_run_locally(self):
        rc, lines, out = self.run_job(step("other", uses="actions/checkout@v4"), args=("--base", "origin/main"))
        self.assertEqual(self.verdicts(lines), ["not run locally"], out)


class RealChecks(unittest.TestCase):
    def test_every_checks_step_gets_one_line(self):
        sys.path.insert(0, HERE)
        from workflow_steps import job_block, step_blocks
        with open(CHECKS, encoding="utf-8") as f:
            want = len(step_blocks(job_block(f.read(), "checks")))
        done = subprocess.run([sys.executable, CI_JOB, "checks", "--plan", "--base", "origin/main"],
                              cwd=os.path.join(HERE, ".."), capture_output=True, text=True, env=ENV)
        lines = done.stdout.splitlines()
        self.assertEqual(len(lines), want, done.stdout + done.stderr)
        self.assertGreater(want, 50)
        self.assertTrue(any(ln.startswith("would run") and "STE lint" in ln for ln in lines), done.stdout)
        multi = [ln for ln in lines if "Opt-in CI template fixture suites" in ln]
        self.assertEqual(len(multi), 1, done.stdout)
        self.assertFalse(multi[0].startswith("skipped"), multi[0])


STAMP = os.path.join(HERE, "..", ".github", "stamp.json")


def job_names(text):
    """The job names under `jobs:` in a workflow text: keys at two spaces, until the next top-level key."""
    names, inside = [], False
    for line in text.splitlines():
        if re.match(r"^jobs:\s*$", line):
            inside = True
        elif inside and re.match(r"^\S", line):
            inside = False
        elif inside:
            m = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
            if m:
                names.append(m.group(1))
    return names


def missing_required(required, jobs):
    """The required check names no job carries. merge.py waits forever on such a name."""
    return [name for name in required if name not in jobs]


class RequiredChecks(unittest.TestCase):
    def test_every_required_check_in_stamp_json_is_a_job_of_checks_yml(self):
        import json
        with open(STAMP, encoding="utf-8") as f:
            required = json.load(f)["merge"]["requiredChecks"]
        with open(CHECKS, encoding="utf-8") as f:
            jobs = job_names(f.read())
        self.assertGreater(len(jobs), 10, jobs)
        self.assertEqual(missing_required(required, jobs), [])

    def test_a_required_name_that_no_job_carries_is_named(self):
        # The red case: the old job name after a rename. The check must name it.
        jobs = job_names("name: t\njobs:\n  scope:\n    runs-on: x\n  checks:\n    runs-on: x\non: push\n")
        self.assertEqual(jobs, ["scope", "checks"])
        self.assertEqual(missing_required(["scope", "gates", "checks"], jobs), ["gates"])


def plan_lint(root, wf_text, extra=()):
    """Lines of `ci-job lane --lint --plan` over a workflow text."""
    path = os.path.join(root, "wf.yml")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(wf_text)
    done = subprocess.run([sys.executable, CI_JOB, "lane", "--lint", "--plan", "--workflow", path, *extra], cwd=root,
                          capture_output=True, text=True, env=ENV, timeout=60)
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
                m = re.match(r"^        run: (python3 (?:lint|actions)/\S+\.py\b.*|bin/ste-changed\b.*)$", line)
                if m and "mutate" not in m.group(1):
                    want.append(name)
                if re.match(r"^        uses: \S*actions/ste-lint\s*$", line):
                    want.append(name)  # the STE action: ci-job runs bin/ste-changed in its place
        self.assertGreater(len(want), 20)
        done = subprocess.run([sys.executable, CI_JOB, "checks", "--lint", "--plan", "--base", "origin/main"],
                              cwd=os.path.join(HERE, ".."), capture_output=True, text=True, env=ENV)
        lines = done.stdout.splitlines()
        self.assertEqual(len(lines), len(want), done.stdout + done.stderr)
        for expected in want:
            self.assertTrue(any(ln.split("  ", 1)[-1].startswith(expected) or ("  " + expected) in ln for ln in lines),
                            "missing %r in %s" % (expected, done.stdout))
        self.assertNotIn("test_guard", done.stdout)

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


if __name__ == "__main__":
    unittest.main()
