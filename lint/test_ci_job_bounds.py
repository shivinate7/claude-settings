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

Ends of a run: a step's child outlives neither ci-job's SIGTERM nor its SIGINT (SignalsToCiJob), and merge's whole-run backstop
(merge.ci_job_run, merge.pre_ready_rows) ends the step's tree too, keeps the FAIL line of a step that finished, and gives an
unfinished step's row its bound (BackstopOfTheRun). CI_JOB_STEP_SECONDS past threading.TIMEOUT_MAX is one unknown line, exit 2
(StepBoundLimit).
"""
import contextlib, io, os, shutil, signal, subprocess, sys, threading, time, unittest, unittest.mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_ci_job as tcj  # noqa: E402  the Job fixture and the step helpers (one home); importing it runs none of its cases
sys.path.insert(0, os.path.join(HERE, "..", "merge"))
import merge  # noqa: E402  the pre-ready run's ci_job_run and pre_ready_rows (merge/merge.py)

BOUND = 3  # seconds: CI_JOB_STEP_SECONDS for the hang cases
BACKSTOP = 5  # seconds: merge's whole-run bound in the backstop cases, past a step's start-up and short of its 30-60 s work
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


def wait_until(condition):
    """True once `condition()` holds, polled up to 100 times, 0.05 s apart: a condition, not a clock. False when it never holds."""
    for _ in range(100):
        if condition():
            return True
        time.sleep(0.05)
    return bool(condition())


def recorded_pid(path):
    """The pid a step wrote to `path`, or None while the file is missing or still empty."""
    try:
        with open(path, encoding="utf-8") as f:
            return int(f.read())
    except (OSError, ValueError):
        return None


def end_tree(pid):
    """Ends `pid` and its process group, unless the group is this case's own. Cleanup only: a case that leaves a sleeper alive holds its folder open."""
    if pid is None:
        return
    try:
        group = os.getpgid(pid)
        if group != os.getpgid(0):
            os.killpg(group, signal.SIGKILL)
    except OSError:
        pass
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


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


class SignalsToCiJob(tcj.Job):
    """ci-job ends by SIGTERM or SIGINT: a child its bounded step started ends with it. The case reads ci-job's own exit first,
    so a signal that never reached ci-job reads as that failure, not as a leaked child."""

    def end_by(self, sig):
        argv, env = self.job_call(tree_step("tree"), args=("--step", "tree"), env={"CI_JOB_STEP_SECONDS": "60"})
        pid_path = os.path.join(self.root, "child.pid")
        with open(os.path.join(self.root, "job.out"), "wb") as out_handle:  # its own session: a group kill reaches only this run
            proc = subprocess.Popen(argv, cwd=self.root, env=env, stdout=out_handle, stderr=subprocess.STDOUT, start_new_session=True)
            self.addCleanup(tcj.QuietStepKeepsTheStallWatchFed.kill_group, proc)
            self.assertTrue(wait_until(lambda: recorded_pid(pid_path) is not None), "the step never started its child, so the signal is not read")
            child = recorded_pid(pid_path)
            self.addCleanup(end_tree, child)
            proc.send_signal(sig)
            try:
                proc.wait(timeout=120)
            except subprocess.TimeoutExpired:
                self.fail(f"ci-job did not exit within 120 s of {sig.name}")
        self.assertTrue(wait_until(lambda: not alive(child)),
                        f"the step's child {child} runs after ci-job exited on {sig.name}: ci-job ended without its step's tree")

    def test_sigterm_to_ci_job_ends_the_step_tree(self):
        self.end_by(signal.SIGTERM)

    def test_sigint_to_ci_job_ends_the_step_tree(self):
        self.end_by(signal.SIGINT)


class StepBoundLimit(tcj.Job):
    """A CI_JOB_STEP_SECONDS past threading.TIMEOUT_MAX is one unknown line, exit 2, and no step runs: a timer cannot hold it.
    A bound at the limit still runs the step."""

    def test_a_bound_past_the_timer_limit_is_one_unknown_line_and_exit_two(self):
        over = str(int(threading.TIMEOUT_MAX) + 1)
        rc, lines, out = self.run_job(tcj.step("quick", "echo quick > quick.txt"), args=("--step", "quick"), env={"CI_JOB_STEP_SECONDS": over})
        self.assertEqual(rc, 2, f"a bound of {over} s was not refused: exit {rc}\n{out}")
        self.assertEqual(len(lines), 1, f"the refusal is not one line:\n{out}")
        self.assertTrue(lines[0].startswith("unknown") and "CI_JOB_STEP_SECONDS" in lines[0], f"the line does not name the bound: {lines[0]!r}")
        self.assertFalse(os.path.exists(os.path.join(self.root, "quick.txt")), "a step ran under a bound the timer cannot hold")

    def test_a_bound_at_the_timer_limit_still_runs_the_step(self):  # control
        at = str(int(threading.TIMEOUT_MAX))
        rc, lines, out = self.run_job(tcj.step("quick", "echo quick > quick.txt"), args=("--step", "quick"), env={"CI_JOB_STEP_SECONDS": at})
        self.assertEqual((rc, self.verdicts(lines)), (0, ["PASS"]), out)


class BackstopOfTheRun(tcj.Job):
    """merge.ci_job_run's backstop, the whole run's bound, ends the run. The step's tree goes with it, the lines of the steps that
    finished are kept, and the row of a step the backstop ended reads its bound. CI_JOB_STEP_SECONDS=60 stays above the backstop,
    so the backstop is the bound that fires. VERDICT_LOG and TMPDIR point into this case's folder for the run."""

    def run_backstop(self, steps, args):
        self.job_call(*steps)  # writes the workflow to wf.yml, as the job "lane"
        wf = os.path.join(self.root, "wf.yml")
        with unittest.mock.patch.dict(os.environ, {"VERDICT_LOG": os.path.join(self.root, "verdict.log"), "TMPDIR": self.root}):
            return merge.ci_job_run(self.root, "lane", "--workflow", wf, *args, bound=BACKSTOP, step_seconds=60)

    def test_a_backstop_expiry_ends_the_steps_child_too(self):
        pid_path = os.path.join(self.root, "child.pid")
        state, _, _, _ = self.run_backstop([tree_step("tree")], ("--step", "tree"))
        self.assertEqual(state, "unknown", "the backstop did not end the run as unknown")
        child = recorded_pid(pid_path)
        self.assertIsNotNone(child, "the step never started its child, so the expiry is not read")
        self.addCleanup(end_tree, child)
        self.assertTrue(wait_until(lambda: not alive(child)),
                        f"the step's child {child} runs after ci_job_run returned on its backstop: the backstop ended ci-job, not the step's tree")

    def test_a_backstop_expiry_keeps_the_fail_line_of_a_step_that_finished(self):
        self.addCleanup(lambda: end_tree(recorded_pid(os.path.join(self.root, "child.pid"))))
        state, lines, _, _ = self.run_backstop([tcj.step("bad", "exit 1"), tree_step("slow")], ("--step", "bad", "--step", "slow"))
        self.assertEqual(state, "unknown", "the backstop did not end the run as unknown")
        self.assertTrue(any(line.startswith("FAIL bad") for line in lines),
                        f"the FAIL line of the step that finished was lost when the backstop ended the run: {lines}")

    def test_the_row_of_a_step_the_backstop_ended_reads_its_bound(self):
        self.addCleanup(lambda: end_tree(recorded_pid(os.path.join(self.root, "child.pid"))))
        workflows = os.path.join(self.root, ".github", "workflows")
        os.makedirs(workflows)
        with open(os.path.join(workflows, "checks.yml"), "w", encoding="utf-8", newline="\n") as f:
            f.write(tcj.workflow(tcj.step("bad", "exit 1"), tree_step("slow"), job="checks"))
        with unittest.mock.patch.object(merge, "READY_CI_RUN_SECONDS", BACKSTOP), \
                unittest.mock.patch.dict(os.environ, {"VERDICT_LOG": os.path.join(self.root, "verdict.log"), "TMPDIR": self.root}), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            rows, _ = merge.pre_ready_rows(self.root, 7, "main", ["bad", "slow"], None)
        self.assertIsNotNone(recorded_pid(os.path.join(self.root, "child.pid")), "the step never started its child, so the row is not read")
        self.assertEqual([name for _, name, _ in rows], ["bad", "slow"], "the pre-ready run did not read both checks")
        verdict, _, detail = rows[1]
        self.assertEqual(verdict, "unknown")
        self.assertIn(f"did not finish in {BACKSTOP} s", detail, f"the row of the step the backstop ended reads {detail!r}, not its bound")


if __name__ == "__main__":
    unittest.main()
