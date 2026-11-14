#!/usr/bin/env python3
"""Cases for the per-step bound of bin/ci-job --step (roadmap step ready-checks-time-bound).

Run: python3 lint/test_ci_job_bounds.py

CI_JOB_STEP_SECONDS bounds each step that a --step run executes. A step past its bound is killed with its process tree,
prints one line `unknown <step>: did not finish in N s`, and the run exits 2. Each named step has its own bound: a hung
step does not change the verdict of a step that finished on its own. A bound never softens a PASS or a FAIL.

A hang step writes late.txt at BOUND + 5 s, so a run that returns with late.txt absent did not wait the step out. The case
reads a file, not a clock. The start line is read from inside the step: ci-job's stderr goes to a file the step can read.
The fixtures (workflow, step, Job, run folder) come from lint/test_ci_job.py, the one home; this file subclasses its Job.
Linux only: the process-tree case reads /proc, and the suite runs in the Linux checks job.
"""
import os, shutil, subprocess, sys, time, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_ci_job as tcj  # noqa: E402  the Job fixture and the step helpers (one home); importing it runs none of its cases

BOUND = 3  # seconds: CI_JOB_STEP_SECONDS for the hang cases
LATE = BOUND + 5  # a hang step writes late.txt this many seconds in
BOUND_ENV = {"CI_JOB_STEP_SECONDS": str(BOUND)}
unittest.addModuleCleanup(shutil.rmtree, tcj.RUN_FOLDER, True)  # the run folder that importing test_ci_job made


def hang(name, late=LATE):
    """A step that starts, sleeps `late` s, then writes late.txt."""
    return tcj.step(name, "echo started > started.txt\nsleep %d\necho late > late.txt" % late)


def tree_step(name):
    """A step that starts a child with its output sent away, records the child's pid, then waits 30 s in the foreground. The child
    outlives the step's own wait on the old code, which ends the step and leaves the child running."""
    return tcj.step(name, "sleep 300 >/dev/null 2>&1 &\necho $! > child.pid\nsleep 30")


def probe(name, err_path):
    """A step that writes seen.txt: yes when ci-job's stderr file already holds `start: <name>` line, else no."""
    return tcj.step(name, "grep -qx 'start: %s' '%s' && echo yes > seen.txt || echo no > seen.txt" % (name, err_path))


def alive(pid):
    """True while `pid` runs. A zombie has ended: only its parent has not read its exit."""
    try:
        with open("/proc/%d/stat" % pid, encoding="utf-8") as f:
            return f.read().rsplit(")", 1)[1].split()[0] != "Z"
    except FileNotFoundError:
        return False


def first_line(lines):
    return lines[0] if lines else "(no line printed)"


class StepBound(tcj.Job):
    """`--step` with CI_JOB_STEP_SECONDS: a step past its bound reads unknown, is killed with its children, and the run goes on
    to the next named step. Controls: a step under its bound keeps its PASS or FAIL, and its start line comes before it runs."""

    def test_a_step_past_its_bound_reads_unknown_naming_the_step_and_its_bound(self):
        rc, lines, out = self.run_job(hang("slow"), args=("--step", "slow"), env=BOUND_ENV)
        self.assertRegex(first_line(lines), rf"^unknown\s+slow: did not finish in {BOUND} s$", out)
        self.assertEqual(rc, 2, out)

    def test_a_step_past_its_bound_is_killed_before_it_runs_on(self):
        self.run_job(hang("slow"), args=("--step", "slow"), env=BOUND_ENV)
        self.assertTrue(os.path.exists(os.path.join(self.root, "started.txt")), "the step never started, so the kill is not read")
        self.assertFalse(os.path.exists(os.path.join(self.root, "late.txt")),
                         f"the step ran on to its end at {LATE} s: it was not killed at its {BOUND} s bound")

    def test_a_child_of_a_killed_step_is_gone_when_ci_job_returns(self):
        argv, env = self.job_call(tree_step("tree"), args=("--step", "tree"), env=BOUND_ENV)
        with open(os.path.join(self.root, "job.out"), "wb") as out_handle:  # its own session: a group kill reaches only this run
            proc = subprocess.Popen(argv, cwd=self.root, env=env, stdout=out_handle, stderr=subprocess.STDOUT, start_new_session=True)
            self.addCleanup(tcj.QuietStepKeepsTheStallWatchFed.kill_group, proc)
            proc.wait(timeout=120)
        pid_path = os.path.join(self.root, "child.pid")
        self.assertTrue(os.path.exists(pid_path), "the step never started its child, so the tree is not read")
        with open(pid_path, encoding="utf-8") as f:
            pid = int(f.read())
        for _ in range(100):  # a condition, not a clock: the kill may land a moment after ci-job starts its exit
            if not alive(pid):
                break
            time.sleep(0.05)
        self.assertFalse(alive(pid), "a child of the step is still running after ci-job returned: the bound killed the shell only")

    def test_each_named_step_has_its_own_bound(self):
        rc, lines, out = self.run_job(hang("slow"), tcj.step("fast", "echo fast > fast.txt"),
                                      args=("--step", "slow", "--step", "fast"), env=BOUND_ENV)
        self.assertTrue(os.path.exists(os.path.join(self.root, "fast.txt")), "the step after the hung one never ran")
        self.assertEqual(self.verdicts(lines), ["unknown", "PASS"], out)
        self.assertEqual(rc, 2, out)

    def test_a_step_under_its_bound_passes(self):  # control
        rc, lines, out = self.run_job(tcj.step("quick", "sleep 1"), args=("--step", "quick"), env={"CI_JOB_STEP_SECONDS": "10"})
        self.assertEqual((rc, self.verdicts(lines)), (0, ["PASS"]), out)

    def test_a_step_that_fails_under_its_bound_stays_a_fail(self):  # control
        rc, lines, out = self.run_job(tcj.step("bad", "exit 1"), args=("--step", "bad"), env={"CI_JOB_STEP_SECONDS": "10"})
        self.assertEqual((rc, self.verdicts(lines)), (1, ["FAIL"]), out)

    def test_the_start_line_reaches_stderr_before_the_step_runs(self):  # control: ci-job prints it already
        err_path = os.path.join(self.root, "job.err")
        argv, env = self.job_call(probe("probe", err_path), args=("--step", "probe"))
        with open(err_path, "w", encoding="utf-8") as err:
            done = subprocess.run(argv, cwd=self.root, stdout=subprocess.PIPE, stderr=err, text=True, env=env, timeout=120)
        seen = os.path.join(self.root, "seen.txt")
        self.assertTrue(os.path.exists(seen), "the probe step never ran, so the start line is not read")
        with open(seen, encoding="utf-8") as f:
            self.assertEqual(f.read().strip(), "yes", "the start line was not on stderr while the step ran: " + done.stdout)


if __name__ == "__main__":
    unittest.main()
