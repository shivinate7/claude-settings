#!/usr/bin/env python3
"""Suite for `merge --lane-lint`: the lint a lane passes before it joins a batch (lanes-run-no-full-ci-job).

Run: python3 merge/test_lane_lint.py
The lint is bin/ci-job's `checks --lint`, reached through merge.CI_JOB. Each case points CI_JOB at a stub that
prints scripted step lines and exits with a scripted code, so no real lint runs. The stub logs each call, so a
case reads what the tool ran, in which tree, at which head. The repo builder, the fakes and the cloud-session
fixture come from merge/test_merge.py: a case extends that fixture, it does not copy it. The draft step's ready check
(class ReadyChecks) runs the same stub, through CiJobStub.
The SIGTERM case runs merge in a subprocess through HARNESS, which names the same stub; it is the one case that does not patch CI_JOB.
The merge.laneTests cases register their own profile in mutate_guard.REPLAY_PROFILES, for that case only, and their select is a script in the fixture.
Temp files: this run's folder (lint/_test_temp.py), removed at exit.
"""
import atexit, json, os, re, shutil, signal, subprocess, sys, tempfile, time, unittest, unittest.mock, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.append(os.path.join(os.path.dirname(HERE), "lint"))  # append: no lint module shadows one this suite imports
import _test_temp  # noqa: E402  test-temp-standard: this run's folder (lint/_test_temp.py)
import test_merge as tm  # noqa: E402  the git half's fixture and fakes; importing it runs none of its cases
import merge  # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "hooks"))  # merge.py puts hooks on sys.path too; named here for the profile registry
import mutate_guard  # noqa: E402  REPLAY_PROFILES: the one home of a repo's test selector, which merge.laneTests names

RUN_FOLDER = _test_temp.run_folder()
atexit.register(shutil.rmtree, RUN_FOLDER, True)

PASSING = [("PASS", "record slugs"), ("PASS", "ste lint")]
FAILING = [("PASS", "record slugs"), ("FAIL", "comment narration")]
UNKNOWN = [("PASS", "record slugs"), ("unknown", "shellcheck")]

LANE_PROFILE = "lane_fixture"  # the profile name the fixture's merge.laneTests names; LaneLint.use_lane_profile registers it per case
SUITE = "tests/test_p_contract.py"  # a suite the fixture's selector lists for its product file
OTHER_SUITE = "tests/test_q_contract.py"
THIRD_SUITE = "tests/test_r_contract.py"

STUB = '''import json, os, subprocess, sys, time
LOG, STEPS, RC, STEP_LOG, SLEEP, PARENT = __LOG__, __STEPS__, __RC__, __STEP_LOG__, __SLEEP__, os.getppid()
def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True).stdout.strip()
detached = subprocess.run(["git", "symbolic-ref", "-q", "HEAD"], capture_output=True).returncode != 0
with open(LOG, "a", encoding="utf-8") as f:
    print(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd(), "head": git("rev-parse", "HEAD"), "detached": detached}), file=f)
if "--plan" in sys.argv:
    for state, name in STEPS:
        print("would run " + name)
    sys.exit(0)
end = time.time() + SLEEP  # a lint that runs long: it ends after SLEEP s, or at once when the run that started it is gone
while time.time() < end and os.getppid() == PARENT:
    time.sleep(0.05)
lines = ["%-15s %s: stub step" % (state, name) for state, name in STEPS]
print("\\n".join(lines))
if RC == 1:
    with open(STEP_LOG, "w", encoding="utf-8") as f:
        f.write("\\n".join(lines) + "\\n")
    print("log=" + STEP_LOG)  # the last line: the refusal reads it as the failing run's log
sys.exit(RC)
'''

# merge.py fixes CI_JOB at import, so a subprocess run names the stub here, before main runs. Same argv and exit code as merge.py's __main__.
HARNESS = '''import sys
sys.path.insert(0, __HERE__)
import merge
merge.CI_JOB = __STUB__
sys.exit(merge.main(sys.argv[1:]))
'''

# Added to STUB before its verdict lines: one `start:` line per step on stderr, then a wait for the GO file. The wait is
# a bound only (20 s): the case creates GO once it has read the first announcement from merge's stderr, so the lint
# cannot end before the announcement is read.
PROGRESS = '''GO = __GO__
for _state, _name in STEPS:
    print("start: " + _name, file=sys.stderr, flush=True)
end = time.time() + 20
while not os.path.exists(GO) and time.time() < end:
    time.sleep(0.05)
'''

WORKFLOW = """name: t
on: push
jobs:
  checks:
    runs-on: ubuntu-latest
    steps:
      - name: Lint one
        run: python3 lint/a.py
      - name: Make lint-py
        run: make lint-py
      - name: Lint two
        run: python3 lint/b.py
"""


def pass_lines(text):
    return [line for line in text.splitlines() if line.startswith("PASS:")]


class NoLock:
    """The lane run takes no merge lock: a lock call fails the case."""
    def acquire(self, *args, **kwargs):
        raise AssertionError("merge --lane-lint took the merge lock")

    def release(self, *args, **kwargs):
        raise AssertionError("merge --lane-lint released a merge lock")

    def unlock(self, *args, **kwargs):
        raise AssertionError("merge --lane-lint unlocked a merge lock")


class LintStepNames(unittest.TestCase):
    """merge's lint_steps reads each `would run ` line of ci-job's plan as a step name. The plan's summary line names no
    step, so it must not come back as one."""

    def test_the_plan_summary_is_not_a_step_name(self):
        root = tempfile.mkdtemp(prefix="lint-steps-", dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, root, True)
        os.makedirs(os.path.join(root, ".github", "workflows"))
        tm.put(os.path.join(root, ".github", "workflows", "checks.yml"), WORKFLOW)
        names = merge.lint_steps(root, "origin/main")
        self.assertEqual(names, {"Lint one", "Lint two"}, "lint_steps read a line that is no step: %s" % sorted(names - {"Lint one", "Lint two"}))


class CiJobStub:
    """The stub ci-job of this suite, for a class with self.t. Its setUp calls init_stub(). use_ci_job points merge.CI_JOB at
    a stub that prints `steps` and exits `rc`; lint_calls reads back every run the stub logged, never a plan."""

    def init_stub(self):
        self.log = os.path.join(self.t, "ci-calls.jsonl")
        self.stub = os.path.join(self.t, "ci-job-stub.py")
        self.step_log = os.path.join(self.t, "ci-job-step.log")

    def write_stub(self, steps, rc, sleep=0):
        """Write the stub ci-job: it prints `steps` ((state, step name) pairs), exits with `rc`, and runs `sleep` s first when it is set."""
        text = STUB.replace("__STEP_LOG__", repr(self.step_log)).replace("__LOG__", repr(self.log))
        tm.put(self.stub, text.replace("__STEPS__", repr(steps)).replace("__RC__", repr(rc)).replace("__SLEEP__", repr(sleep)))
        return self.stub

    def use_ci_job(self, steps, rc):
        """merge.CI_JOB becomes a stub that prints `steps` ((state, step name) pairs) and exits with `rc`."""
        self.write_stub(steps, rc)
        patch = unittest.mock.patch.object(merge, "CI_JOB", self.stub)
        patch.start()
        self.addCleanup(patch.stop)

    def lint_calls(self):
        """The stub's calls that ran the lint, not the plan."""
        if not os.path.exists(self.log):
            return []
        with open(self.log, encoding="utf-8") as f:
            calls = [json.loads(line) for line in f if line.strip()]
        return [c for c in calls if "--plan" not in c["argv"]]


class LaneLint(CiJobStub, tm.CloudSession):
    @classmethod
    def setUpClass(cls):
        unittest.TestCase.setUpClass()  # not CloudSession's: it would make a second run folder
        cls.run_dir = RUN_FOLDER

    def setUp(self):
        with unittest.mock.patch.object(tempfile, "tempdir", RUN_FOLDER):  # Env.setUp makes its repos in the temp dir: keep them in this run's folder
            super().setUp()
        self.lock = NoLock()
        self.init_stub()

    def run_lane(self, *argv, cloud=False):
        """-> (rc, stdout and stderr together) of merge in the lane checkout. A refused command line fails the case with its reason."""
        rc, out, err = self.run_main(*argv, **({} if cloud else {"CLAUDE_CODE_REMOTE": None}))
        if rc == 2 and "error:" in err:  # argparse refused the command line
            last = err.strip().splitlines()[-1]
            if "unrecognized arguments" in last and "--lane-lint" in last:
                self.fail("the mode does not exist: " + last)
            self.fail("argparse refused the command line: " + last)
        return rc, out + err

    def lint_run(self, *argv, base="main", head=None, cloud=False):
        """Run merge in the lane checkout. -> (rc, stdout and stderr together). The lint must have run once, as
        `checks --lint --base origin/<base>`, in a detached tree at the head, and that tree must be gone afterwards."""
        head = head or self.head("feat")
        if os.path.exists(self.log):
            os.remove(self.log)
        rc, text = self.run_lane(*argv, cloud=cloud)
        runs = self.lint_calls()
        self.assertEqual(len(runs), 1, "the lint ran %d times, want once: %s" % (len(runs), text))
        run = runs[0]
        self.assertEqual(run["argv"], ["checks", "--lint", "--base", "origin/" + base])
        self.assertEqual(run["head"], head)
        self.assertTrue(run["detached"], "the lint ran on a branch, not a detached tree")
        self.assertNotEqual(run["cwd"], os.path.realpath(self.co), "the lint ran in the lane checkout")
        self.assertFalse(os.path.exists(run["cwd"]), "the lint tree is still on disk")
        self.assertFalse(tm.tree_listed(self.co, run["cwd"]), "git still lists the lint tree")
        self.assertEqual(self.worktrees(), 1)
        return rc, text

    def push_release_branch(self):
        sh = tm.sh
        sh(self.other, "git", "fetch", "-q", "origin")
        sh(self.other, "git", "push", "-q", "origin", "origin/main:refs/heads/release")

    def progress_run(self, steps, rc, *argv):
        """Run merge in a subprocess through HARNESS, with the stub of `steps` (see PROGRESS). -> (rc, stdout, stderr).
        stderr is read live: the case creates the GO file at the first `start:` line, so a stderr that merge captures
        instead of passing on reads to the end only after the stub's bound."""
        go = os.path.join(self.t, "go")
        text = STUB.replace("__STEP_LOG__", repr(self.step_log)).replace("__LOG__", repr(self.log))
        text = text.replace("__STEPS__", repr(steps)).replace("__RC__", repr(rc)).replace("__SLEEP__", repr(0))
        tm.put(self.stub, text.replace("lines = [", PROGRESS.replace("__GO__", repr(go)) + "lines = [", 1))
        harness = os.path.join(self.t, "lane_lint_progress.py")
        tm.put(harness, HARNESS.replace("__HERE__", repr(HERE)).replace("__STUB__", repr(self.stub)))
        env = {**os.environ, "CLAUDE_CONFIG_DIR": self.cfg}
        env.pop("CLAUDE_CODE_REMOTE", None)
        proc = subprocess.Popen([sys.executable, harness, *argv], cwd=self.co, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(self.stop_run, proc)
        err = []
        for line in proc.stderr:
            err.append(line)
            if line.startswith("start:"):
                open(go, "w", encoding="utf-8").close()
                break
        out, rest = proc.communicate(timeout=120)
        return proc.returncode, out, "".join(err) + rest

    def test_a_progress_line_from_ci_job_reaches_the_callers_stderr_live_and_the_pass_still_reads_from_stdout(self):
        rc, out, err = self.progress_run(PASSING, 0, "--lane-lint", self.head("feat"))
        self.assertTrue(any(line.startswith("start:") for line in err.splitlines()),
                        "no ci-job start line reached merge's stderr while the lint ran: " + err)
        self.assertEqual(len(self.lint_calls()), 1, out + err)
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(len(pass_lines(out)), 1, out)
        self.assertEqual([line for line in out.splitlines() if line.startswith("start:")], [], out)

    def test_a_failed_step_with_a_progress_line_still_refuses_and_names_the_step(self):
        rc, out, err = self.progress_run(FAILING, 1, "--lane-lint", self.head("feat"))
        self.assertTrue(any(line.startswith("start:") for line in err.splitlines()),
                        "no ci-job start line reached merge's stderr while the lint ran: " + err)
        self.assertEqual(rc, 1, out + err)
        self.assertTrue(any("comment narration" in line and "FAIL" in line for line in (out + err).splitlines()), out + err)
        self.assertEqual(pass_lines(out), [], out)

    def test_a_passing_lint_prints_one_pass_line_naming_head_and_base(self):
        self.use_ci_job(PASSING, 0)
        rc, out = self.lint_run("--lane-lint", "7")
        self.assertEqual(rc, 0, out)
        lines = pass_lines(out)
        self.assertEqual(len(lines), 1, out)
        self.assertIn(self.head("feat")[:7], lines[0])
        self.assertIn("main", lines[0])
        self.assertIn("batch runner", lines[0])

    def test_a_lane_lint_merges_nothing_takes_no_lock_and_waits_for_no_check(self):
        self.use_ci_job(PASSING, 0)
        before = self.refs()
        rc, out = self.lint_run("--lane-lint", "7")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.refs(), before, "the lane run pushed a ref")
        self.assertFalse(getattr(self.host, "merged", False))
        self.assertEqual(self.host.readies, [])
        self.assertEqual(self.host.waits, [])

    def test_a_failed_step_refuses_names_each_failing_step_and_gives_the_remedy(self):
        self.use_ci_job(FAILING, 1)
        before = self.refs()
        rc, out = self.lint_run("--lane-lint", "7")
        self.assertEqual(rc, 1, out)
        self.assertTrue(any("comment narration" in line and "FAIL" in line for line in out.splitlines()), out)
        self.assertRegex(out, r"(?i)push")
        self.assertRegex(out, r"(?i)again")
        self.assertEqual(pass_lines(out), [], out)
        self.assertEqual(self.refs(), before, "a refused lane pushed a ref")

    def test_an_unknown_reason_does_not_lift_a_failed_step(self):
        self.use_ci_job(FAILING, 1)
        rc, out = self.lint_run("--lane-lint", "7", "--lint-unknown-ok", "shellcheck is not on this box")
        self.assertEqual(rc, 1, out)
        self.assertEqual(pass_lines(out), [], out)

    def test_an_unknown_step_refuses_and_never_reads_as_a_pass(self):
        self.use_ci_job(UNKNOWN, 2)
        rc, out = self.lint_run("--lane-lint", "7")
        self.assertEqual(rc, 1, out)
        self.assertTrue(any("shellcheck" in line and "unknown" in line.lower() for line in out.splitlines()), out)
        self.assertEqual(pass_lines(out), [], out)

    def test_an_unknown_step_with_a_reason_passes_with_one_logged_line(self):
        self.use_ci_job(UNKNOWN, 2)
        reason = "shellcheck is not on this box"
        rc, out = self.lint_run("--lane-lint", "7", "--lint-unknown-ok", reason)
        self.assertEqual(rc, 0, out)
        logged = [line for line in out.splitlines() if reason in line]
        self.assertEqual(len(logged), 1, out)
        self.assertIn("unknown", logged[0].lower())
        self.assertEqual(pass_lines(out), [], "an unknown read was printed as a pass")

    def test_a_blank_unknown_reason_still_refuses(self):
        self.use_ci_job(UNKNOWN, 2)
        for reason in ("", "   "):
            with self.subTest(reason=reason):
                rc, out = self.lint_run("--lane-lint", "7", "--lint-unknown-ok", reason)
                self.assertEqual(rc, 1, out)
                self.assertEqual(pass_lines(out), [], out)

    def test_a_ref_target_lints_against_main_by_default(self):
        self.use_ci_job(PASSING, 0)
        sha = self.head("feat")
        rc, out = self.lint_run("--lane-lint", sha, head=sha)
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(pass_lines(out)), 1, out)

    def test_a_base_flag_names_the_base_the_lint_runs_against_for_a_ref_target(self):
        self.push_release_branch()
        self.use_ci_job(PASSING, 0)
        sha = self.head("feat")
        rc, out = self.lint_run("--lane-lint", sha, "--base", "release", base="release", head=sha)
        self.assertEqual(rc, 0, out)

    def test_a_pr_target_takes_its_head_and_base_from_the_pull_request(self):
        self.push_release_branch()
        self.host.base = "release"
        self.use_ci_job(PASSING, 0)
        rc, out = self.lint_run("--lane-lint", "7", base="release")
        self.assertEqual(rc, 0, out)

    def test_an_exception_in_the_lint_run_still_removes_the_worktree(self):
        self.use_ci_job(PASSING, 0)
        real_sh, seen = merge.sh, []

        def time_out_the_lint(args, *rest, **kwargs):
            if any(isinstance(a, str) and os.path.basename(a) == os.path.basename(self.stub) for a in args):
                cwd = kwargs.get("cwd")
                seen.append((cwd, bool(cwd) and os.path.isdir(cwd)))
                raise subprocess.TimeoutExpired(args, 1)
            return real_sh(args, *rest, **kwargs)

        with unittest.mock.patch.object(merge, "sh", time_out_the_lint):
            try:
                rc, out = self.run_lane("--lane-lint", "7")
            except subprocess.TimeoutExpired:
                rc, out = None, ""  # the exception may leave the tool: the worktree check below still applies
        self.assertTrue(seen, "the lint run never started, so the case proves nothing")
        cwd, existed = seen[0]
        self.assertIsNotNone(cwd, "the lint run had no directory")
        self.assertTrue(existed, "the lint tree was not on disk when the lint run failed")
        self.assertNotEqual(rc, 0, "an exception in the lint run read as a pass")
        self.assertEqual(pass_lines(out), [])
        self.assertFalse(os.path.exists(cwd), "the lint tree is still on disk after an exception")
        self.assertFalse(tm.tree_listed(self.co, cwd), "git still lists the lint tree after an exception")
        self.assertEqual(self.worktrees(), 1)

    def stop_run(self, proc):
        """Cleanup for a run this case started: it is ours, so a live one is killed. The stub ends by itself when its run is gone."""
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=30)

    @unittest.skipIf(os.name == "nt", "SIGTERM is not delivered as a signal on Windows: a send ends the process at once")
    def test_a_sigterm_during_the_lint_removes_the_lint_tree_and_its_temp_dir(self):
        self.write_stub(PASSING, 0, sleep=120)
        harness = os.path.join(self.t, "lane_lint_run.py")
        tm.put(harness, HARNESS.replace("__HERE__", repr(HERE)).replace("__STUB__", repr(self.stub)))
        tmp_root = tempfile.mkdtemp(dir=self.run_dir, prefix="sigterm-")  # the lint tree's temp dir lands here, not in the system temp dir
        env = {**os.environ, "CLAUDE_CONFIG_DIR": self.cfg, "TMPDIR": tmp_root, "TMP": tmp_root, "TEMP": tmp_root}
        env.pop("CLAUDE_CODE_REMOTE", None)
        text_path = os.path.join(self.t, "lane-lint-run.txt")
        with open(text_path, "w", encoding="utf-8") as text:
            proc = subprocess.Popen([sys.executable, harness, "--lane-lint", self.head("feat")], cwd=self.co, env=env,
                                    stdout=text, stderr=subprocess.STDOUT)
        self.addCleanup(self.stop_run, proc)

        def run_text():
            with open(text_path, encoding="utf-8") as f:
                return f.read()

        deadline = time.time() + 60
        while not self.lint_calls() and proc.poll() is None and time.time() < deadline:
            time.sleep(0.05)
        self.assertIsNone(proc.poll(), "the run ended before its lint started: " + run_text())
        self.assertTrue(self.lint_calls(), "the lint did not start within 60 s: " + run_text())
        lint_tree = self.lint_calls()[0]["cwd"]
        temp_dir = os.path.dirname(lint_tree)
        self.assertTrue(os.path.isdir(lint_tree), "the lint tree was not on disk while the lint ran")
        self.assertEqual(self.worktrees(), 2, "git did not list the lint tree while the lint ran")

        proc.send_signal(signal.SIGTERM)
        try:
            rc = proc.wait(timeout=60)
        except subprocess.TimeoutExpired:
            self.fail("the run did not exit within 60 s of SIGTERM: " + run_text())
        out = run_text()
        self.assertNotEqual(rc, 0, "SIGTERM read as a clean exit: " + out)
        self.assertEqual(pass_lines(out), [], out)
        self.assertEqual(self.worktrees(), 1, "git still lists the lint tree after SIGTERM: " + out)
        self.assertFalse(tm.tree_listed(self.co, lint_tree), "git still lists the lint tree after SIGTERM")
        self.assertFalse(os.path.exists(lint_tree), "the lint tree is still on disk after SIGTERM")
        self.assertFalse(os.path.exists(temp_dir), "the lint tree's temp dir is still on disk after SIGTERM")
        self.assertEqual([n for n in os.listdir(tmp_root) if n.startswith("merge-wt-")], [], "a merge temp dir is left after SIGTERM")

    def has_local_branch(self, name):
        return subprocess.run(["git", "-C", self.co, "rev-parse", "-q", "--verify", f"refs/heads/{name}"], capture_output=True).returncode == 0

    def local_feat_one_past_origin(self):
        """Make the lane checkout's local feat one commit past origin/feat. -> (local sha, origin sha)."""
        tm.sh(self.co, "git", "checkout", "-q", "-b", "feat", "origin/feat")
        tm.put(os.path.join(self.co, "local-only.txt"), "committed here, not pushed\n")
        tm.sh(self.co, "git", "add", "-A")
        tm.sh(self.co, "git", "commit", "-q", "-m", "local only")
        return tm.sh(self.co, "git", "rev-parse", "feat"), tm.sh(self.co, "git", "rev-parse", "origin/feat")

    def test_a_bare_branch_name_with_no_local_branch_lints_origin(self):
        self.use_ci_job(PASSING, 0)
        self.assertFalse(self.has_local_branch("feat"), "the case needs no local feat")
        rc, out = self.lint_run("--lane-lint", "feat", head=self.head("feat"))
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(pass_lines(out)), 1, out)

    def test_a_bare_branch_name_refuses_when_local_and_origin_differ_and_names_both_shas(self):
        local, origin = self.local_feat_one_past_origin()
        self.use_ci_job(PASSING, 0)
        before = self.refs()
        rc, out = self.run_lane("--lane-lint", "feat")
        self.assertEqual(self.lint_calls(), [], "a bare name linted its local branch while origin/feat differs: " + out)
        self.assertNotEqual(rc, 0, "a bare name whose local branch differs from origin/feat read as a pass: " + out)
        self.assertEqual(pass_lines(out), [], out)
        self.assertIn(local[:7], out, "the refusal does not name the local sha")
        self.assertIn(origin[:7], out, "the refusal does not name the origin sha")
        self.assertEqual(self.refs(), before, "a refused lane pushed a ref")

    def test_an_explicit_origin_ref_is_taken_as_given_while_the_local_branch_differs(self):
        _, origin = self.local_feat_one_past_origin()
        self.use_ci_job(PASSING, 0)
        rc, out = self.lint_run("--lane-lint", "origin/feat", head=origin)
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(pass_lines(out)), 1, out)

    def test_a_full_sha_is_taken_as_given_while_the_local_branch_differs(self):
        _, origin = self.local_feat_one_past_origin()
        self.use_ci_job(PASSING, 0)
        rc, out = self.lint_run("--lane-lint", origin, head=origin)
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(pass_lines(out)), 1, out)

    def test_a_failed_lint_refusal_shows_the_ci_job_log_line(self):
        self.use_ci_job(FAILING, 1)
        rc, out = self.lint_run("--lane-lint", "7")
        self.assertEqual(rc, 1, out)
        self.assertTrue(os.path.exists(self.step_log), "the stub wrote no step log")
        self.assertIn("log=" + self.step_log, out.splitlines(), out)

    def test_a_cloud_lane_session_with_no_merge_role_may_run_lane_lint(self):
        self.use_ci_job(PASSING, 0)
        rc, out = self.lint_run("--lane-lint", "7", cloud=True)
        self.assertNotIn("may not merge", out)
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(pass_lines(out)), 1, out)
        rc, out, err = self.run_main("7", "--confirm")  # control: the same cloud session may not merge, so the role check is live
        self.assertEqual(rc, 1, out + err)
        self.assertIn("may not merge", out + err)

    def test_the_hand_off_refusal_names_lane_lint(self):
        rc, out, err = self.run_main("7", "--confirm")
        self.assertEqual(rc, 1, out + err)
        self.assertIn("may not merge", err)
        self.assertIn("--lane-lint", err)

    def test_the_role_refusal_names_lane_lint_and_no_valid_tier(self):
        rc, out, err = self.run_main("--role", "lane")
        self.assertEqual(rc, 1, out + err)
        self.assertIn("--lane-lint", err)
        self.assertNotIn("coordinator", err.lower())
        self.assertNotIn("batch-runner", err.lower())
        self.assertFalse(os.path.exists(self.role_file), "a refused role wrote the role file")

    # merge.laneTests: after the lint passes, the lane's head runs the suites its profile's select lists (contract: merge.lane_lint).

    def use_lane_profile(self, select=None, install=None):
        """Register the fixture profile in mutate_guard.REPLAY_PROFILES for this case. Its select is tools/lane_select.py, in the
        checkout (or `select`, when a case names another argv); its suites are test_*.py files run with this interpreter; its install
        is `install` (an argv, with {deps} the install folder), or nothing. The dict is patched in place, so a name that bound it at
        import sees the entry too."""
        profile = {"code": r"^src/.*\.py$", "tests": r"(^|/)test_[^/]*\.py$", "argv": [sys.executable, "{suite}"],
                   "classify": "fail_line", "install": install, "sparse_skip": [],
                   "select": select or [sys.executable, "tools/lane_select.py", "{path}"]}
        patch = unittest.mock.patch.dict(mutate_guard.REPLAY_PROFILES, {LANE_PROFILE: profile})
        patch.start()
        self.addCleanup(patch.stop)

    def select_text(self, listed, fails, prefix="src/", helper=None):
        """The fixture selector. It logs each path it is asked about, then prints `listed` for a path under `prefix`, or exits 3 when
        `fails`. With `helper` ({folder, module}: a folder relative to the selector's own file), it imports the module from that folder
        after the log line, as q_max's selector loads typescript beside itself: a missing module is a traceback and a non-zero exit."""
        head = "import sys\nwith open(%r, 'a', encoding='utf-8') as log:\n    log.write(sys.argv[1] + '\\n')\n" % self.select_log
        if helper:
            head = ("import os\n" + head + "sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), %r))\n"
                    "import %s\n" % (helper["folder"], helper["module"]))
        if fails:
            return head + "sys.exit(3)\n"
        body = "".join("    print(%r)\n" % name for name in listed) or "    pass\n"
        return head + "if sys.argv[1].startswith(%r):\n" % prefix + body

    def suite_text(self, name, mode):
        """A fixture suite. It logs its path and its folder first, then passes ("pass"), prints a FAIL line and exits 1 ("fail"),
        or dies with no FAIL line ("crash")."""
        head = "import os\nwith open(%r, 'a', encoding='utf-8') as log:\n    log.write(%r + ' ' + os.getcwd() + '\\n')\n" % (self.suite_log, name)
        end = {"pass": "print('ok')\n",
               "fail": "print('FAIL: %s: src/p.py holds the wrong value')\nraise SystemExit(1)\n" % name,
               "crash": "raise RuntimeError('the suite died')\n"}[mode]
        return head + end

    def lane_fixture(self, listed=(), suites=None, feat_suites=None, select_fails=False, laneTests=LANE_PROFILE,
                     lane=None, select_prefix="src/", base_files=None, lane_deletes=(), lane_renames=None,
                     lane_listed=None, select_argv=None, config_text=None, helper=None, install=None):
        """The laneTests fixture, one call per case. origin/main gets the repo's own parts: the config, with merge.laneTests `laneTests`
        (None: the field is absent, or `config_text` is written as the file), tools/lane_select.py, the profile's select, which lists
        `listed` for a path under `select_prefix` or exits 3 when `select_fails`, and which imports `helper` ({folder, module}) when
        given; `suites` ({path: mode}), suites the lane does not touch; and `base_files` ({path: text}), product files the base holds.
        origin/feat gets one commit on top: `lane` ({path: text}, default src/p.py, the product file the lane changes), `feat_suites`
        ({path: mode}), suites the lane itself adds, and `lane_listed`, a selector the lane writes in place of the base's. Then
        `lane_deletes` (paths) and `lane_renames` ({old: new}) go in a second commit. `select_argv` replaces the profile's select, and
        `install` is the profile's install argv. A mode is "pass", "fail" or "crash"."""
        self.select_log = os.path.join(self.t, "select-calls.log")
        self.suite_log = os.path.join(self.t, "suite-runs.log")
        self.use_lane_profile(select_argv, install)
        main = {"tools/lane_select.py": self.select_text(listed, select_fails, select_prefix, helper)}
        if config_text is not None:
            main[".github/stamp.json"] = config_text
        elif laneTests is not None:
            main[".github/stamp.json"] = json.dumps(dict(tm.CONFIG, merge=dict(tm.CONFIG["merge"], laneTests=laneTests)))
        main.update(base_files or {})
        main.update({path: self.suite_text(path, mode) for path, mode in (suites or {}).items()})
        tm.RecordsEnv.on(self, "main", main, "main: the config, the selector, the product files and the suites it lists")
        tm.head_takes_base(self)  # the lane's head holds main's parts, as a lane that merged main does
        feat = dict(lane if lane is not None else ({} if lane_deletes or lane_renames else {"src/p.py": "VALUE = 1\n"}))
        if lane_listed is not None:
            feat["tools/lane_select.py"] = self.select_text(lane_listed, False, select_prefix)
        feat.update({path: self.suite_text(path, mode) for path, mode in (feat_suites or {}).items()})
        if feat:
            tm.RecordsEnv.on(self, "feat", feat, "feat: the lane's changes and the suites it adds")
        if lane_deletes or lane_renames:
            self.lane_moves(lane_deletes, lane_renames or {})

    def lane_moves(self, deletes, renames):
        """One more commit on origin/feat from the second clone, as a lane's own push would make it: `deletes` removed, and `renames`
        ({old: new}) moved with git mv."""
        o = self.other
        tm.sh(o, "git", "fetch", "-q", "origin")
        tm.sh(o, "git", "checkout", "-q", "-B", "feat", "origin/feat")
        for rel in deletes:
            tm.sh(o, "git", "rm", "-q", rel)
        for old, new in renames.items():
            os.makedirs(os.path.dirname(os.path.join(o, new)) or o, exist_ok=True)
            tm.sh(o, "git", "mv", old, new)
        tm.sh(o, "git", "commit", "-qm", "feat: the lane moves product files")
        tm.sh(o, "git", "push", "-q", "origin", "feat")

    def lane_status(self):
        """-> {path: status letter} of the lane's own diff, origin/main...origin/feat, with renames read as a delete and an add (the lane
        lint's reading)."""
        tm.sh(self.co, "git", "fetch", "-q", "origin")
        lines = tm.sh(self.co, "git", "diff", "--name-status", "--no-renames", "origin/main...origin/feat").splitlines()
        return {line.split("\t")[1]: line[0] for line in lines}

    def assert_suite_is_selector_only(self, suite):
        """Scope before subject (P7): the suite is on origin/main and not in the lane's own diff, so only the selector reaches it,
        and it is in the head's tree. A fixture that put the suite in the lane's diff would test a different path."""
        tm.sh(self.co, "git", "fetch", "-q", "origin")
        changed = tm.sh(self.co, "git", "diff", "--name-only", "origin/main...origin/feat").splitlines()
        self.assertNotIn(suite, changed, "the fixture put the suite in the lane's own diff")
        self.assertEqual(tm.sh(self.co, "git", "ls-tree", "--name-only", "origin/main", "--", suite), suite, "the suite is not on main")
        self.assertEqual(tm.sh(self.co, "git", "ls-tree", "--name-only", "origin/feat", "--", suite), suite, "the suite is not at the head")

    def suites_run(self):
        """-> (path, folder) of each suite the fixture logged, in run order. A suite that never ran logs nothing."""
        if not os.path.exists(self.suite_log):
            return []
        with open(self.suite_log, encoding="utf-8") as f:
            return [tuple(line.rstrip("\n").split(" ", 1)) for line in f if line.strip()]

    def suite_names(self):
        return [name for name, _ in self.suites_run()]

    def select_paths(self):
        """-> the paths the fixture selector was asked about, in call order."""
        if not os.path.exists(self.select_log):
            return []
        with open(self.select_log, encoding="utf-8") as f:
            return [line.rstrip("\n") for line in f if line.strip()]

    def test_a_selected_suite_the_lane_did_not_touch_that_fails_at_the_head_refuses_the_lane(self):
        """The lane changes the product file, the selector lists a suite the lane did not touch, and that suite fails at the head.
        The lane lint refuses, names the suite, and runs it in the head's tree, not the lane checkout."""
        self.lane_fixture(listed=[SUITE], suites={SUITE: "fail"})
        self.assert_suite_is_selector_only(SUITE)
        self.use_ci_job(PASSING, 0)
        rc, out = self.lint_run("--lane-lint", "7")
        self.assertIn(SUITE, self.suite_names(), "the selected suite did not run at the head: " + out)
        self.assertEqual(rc, 1, out)
        self.assertTrue(any(SUITE in line and "FAIL" in line for line in out.splitlines()), "the refusal does not name the red suite: " + out)
        self.assertEqual(pass_lines(out), [], out)
        self.assertRegex(out, r"(?i)push")
        self.assertRegex(out, r"(?i)again")
        for _, folder in self.suites_run():
            self.assertNotEqual(os.path.realpath(folder), os.path.realpath(self.co), "the suite ran in the lane checkout")
            self.assertFalse(os.path.exists(folder), "the suite's tree is still on disk after the lint")

    def test_a_selected_suite_that_passes_at_the_head_passes_and_the_pass_line_counts_one_suite(self):
        self.lane_fixture(listed=[SUITE], suites={SUITE: "pass"})
        self.assert_suite_is_selector_only(SUITE)
        self.use_ci_job(PASSING, 0)
        rc, out = self.lint_run("--lane-lint", "7")
        self.assertIn(SUITE, self.suite_names(), "the selected suite did not run at the head: " + out)
        self.assertEqual(rc, 0, out)
        lines = pass_lines(out)
        self.assertEqual(len(lines), 1, out)
        self.assertRegex(lines[0], r"\b1 (?:selected )?suite", "the PASS line does not count the one suite that ran: " + lines[0])

    def test_a_repo_with_no_laneTests_runs_no_suite_and_no_selector_and_passes_as_today(self):  # the control
        self.lane_fixture(listed=[SUITE], suites={SUITE: "fail"}, laneTests=None)
        self.use_ci_job(PASSING, 0)
        rc, out = self.lint_run("--lane-lint", "7")
        self.assertEqual(self.suite_names(), [], "a repo with no laneTests ran a suite: " + out)
        self.assertEqual(self.select_paths(), [], "a repo with no laneTests ran the selector")
        self.assertEqual(rc, 0, out)
        lines = pass_lines(out)
        self.assertEqual(len(lines), 1, out)
        self.assertNotIn("suite", lines[0], "a repo with no laneTests counts suites on its PASS line: " + lines[0])

    def test_an_unknown_laneTests_profile_refuses_and_names_the_field_and_the_profile(self):
        self.lane_fixture(listed=[SUITE], suites={SUITE: "fail"}, laneTests="no_such_profile")
        self.use_ci_job(PASSING, 0)
        rc, out = self.run_lane("--lane-lint", "7")
        self.assertNotEqual(rc, 0, "an unknown laneTests profile read as a pass: " + out)
        self.assertEqual(pass_lines(out), [], out)
        self.assertIn("laneTests", out, "the refusal does not name the field: " + out)
        self.assertIn("no_such_profile", out, "the refusal does not name the unknown profile: " + out)
        self.assertEqual(self.suite_names(), [], "a suite ran for an unknown profile")

    def test_a_selector_that_exits_non_zero_is_unknown_and_refuses_until_the_unknown_flag_lets_it_go_on(self):
        self.lane_fixture(listed=[SUITE], suites={SUITE: "pass"}, select_fails=True)
        self.use_ci_job(PASSING, 0)
        rc, out = self.lint_run("--lane-lint", "7")
        self.assertIn("src/p.py", self.select_paths(), "the selector did not run on the lane's product file: " + out)
        self.assertNotEqual(rc, 0, "a selector that exits non-zero read as a pass: " + out)
        self.assertEqual(pass_lines(out), [], out)
        self.assertRegex(out, r"(?i)unknown", "the refusal does not say the selection is unknown: " + out)
        reason = "the selector is not on this box"
        rc, out = self.lint_run("--lane-lint", "7", "--lint-unknown-ok", reason)
        self.assertEqual(rc, 0, out)
        self.assertEqual(len([line for line in out.splitlines() if reason in line]), 1, "the unknown reason is not logged once: " + out)
        self.assertEqual(pass_lines(out), [], "an unknown selection was printed as a pass")

    def test_a_suite_the_lane_itself_changes_runs_even_when_the_selector_lists_nothing(self):
        self.lane_fixture(listed=[], feat_suites={SUITE: "fail"})
        self.use_ci_job(PASSING, 0)
        rc, out = self.lint_run("--lane-lint", "7")
        self.assertIn(SUITE, self.suite_names(), "the lane's own changed suite did not run: " + out)
        self.assertEqual(rc, 1, out)
        self.assertTrue(any(SUITE in line and "FAIL" in line for line in out.splitlines()), "the refusal does not name the changed suite: " + out)

    def test_a_selected_suite_that_dies_with_no_FAIL_line_refuses_the_lane_and_gets_no_pass(self):
        """The contract says FAIL or unknown, and does not say whether a suite that dies with no FAIL line is red. This case
        asserts only what holds either way: the lane is refused and prints no PASS line."""
        self.lane_fixture(listed=[SUITE], suites={SUITE: "crash"})
        self.use_ci_job(PASSING, 0)
        rc, out = self.lint_run("--lane-lint", "7")
        self.assertIn(SUITE, self.suite_names(), "the selected suite did not run at the head: " + out)
        self.assertNotEqual(rc, 0, "a selected suite that died read as a pass: " + out)
        self.assertEqual(pass_lines(out), [], out)

    def test_a_selected_suite_for_a_non_code_file_the_lane_changes_runs_and_a_red_one_refuses_the_lane(self):
        """Contract item 4: every file the lane adds or changes goes to the selector, not only the files the profile's code regex
        matches. The lane here changes only a non-code file. The selector lists a suite for it; the suite is red; the lane is refused."""
        self.lane_fixture(listed=[SUITE], suites={SUITE: "fail"}, lane={"docs/map/x.md": "# map note\n"}, select_prefix="docs/map/")
        tm.sh(self.co, "git", "fetch", "-q", "origin")
        changed = tm.sh(self.co, "git", "diff", "--name-only", "origin/main...origin/feat").splitlines()
        code = re.compile(mutate_guard.REPLAY_PROFILES[LANE_PROFILE]["code"])
        self.assertIn("docs/map/x.md", changed, "the fixture does not change the non-code file")
        self.assertEqual([path for path in changed if code.search(path)], [],
                         "a changed file matches the profile's code regex, so the case would test a code file")
        self.use_ci_job(PASSING, 0)
        rc, out = self.lint_run("--lane-lint", "7")
        self.assertIn("docs/map/x.md", self.select_paths(), "the selector was not asked about the lane's non-code file: " + out)
        self.assertIn(SUITE, self.suite_names(), "the suite the selector lists for the non-code file did not run: " + out)
        self.assertEqual(rc, 1, out)
        self.assertTrue(any(SUITE in line and "FAIL" in line for line in out.splitlines()), "the refusal does not name the red suite: " + out)
        self.assertEqual(pass_lines(out), [], out)
        self.assertRegex(out, r"(?i)push")
        self.assertRegex(out, r"(?i)again")

    def test_a_selected_suite_for_a_product_file_the_lane_deletes_runs_and_a_red_one_refuses_the_lane(self):
        """A delete is a change, so it goes to the selector. The lane deletes src/p.py, which the base
        holds; the selector lists the red suite for src/p.py; the lane is refused."""
        self.lane_fixture(listed=[SUITE], suites={SUITE: "fail"}, base_files={"src/p.py": "VALUE = 1\n"}, lane={},
                          lane_deletes=["src/p.py"], select_prefix="src/p.py")
        self.assertEqual(self.lane_status().get("src/p.py"), "D", "the fixture does not delete the product file in the lane")
        self.use_ci_job(PASSING, 0)
        rc, out = self.lint_run("--lane-lint", "7")
        self.assertIn("src/p.py", self.select_paths(), "the selector was not asked about the deleted file: " + out)
        self.assertIn(SUITE, self.suite_names(), "the selector's red suite did not run for the deleted file: " + out)
        self.assertEqual(rc, 1, out)
        self.assertTrue(any(SUITE in line and "FAIL" in line for line in out.splitlines()), "the refusal does not name the red suite: " + out)
        self.assertEqual(pass_lines(out), [], out)
        self.assertRegex(out, r"(?i)push")
        self.assertRegex(out, r"(?i)again")

    def test_a_selected_suite_for_a_product_file_the_lane_renames_away_runs_and_a_red_one_refuses_the_lane(self):
        """A rename removes its old path, which is a delete and goes to the selector. The lane moves
        src/p.py to src/q.py. The selector lists the red suite for src/p.py only, so the lane is refused only if the old path is asked."""
        self.lane_fixture(listed=[SUITE], suites={SUITE: "fail"}, base_files={"src/p.py": "VALUE = 1\n"}, lane={},
                          lane_renames={"src/p.py": "src/q.py"}, select_prefix="src/p.py")
        status = self.lane_status()
        self.assertEqual((status.get("src/p.py"), status.get("src/q.py")), ("D", "A"), "the fixture does not rename the product file")
        self.use_ci_job(PASSING, 0)
        rc, out = self.lint_run("--lane-lint", "7")
        self.assertIn("src/p.py", self.select_paths(), "the selector was not asked about the renamed-away file: " + out)
        self.assertIn(SUITE, self.suite_names(), "the selector's red suite did not run for the renamed-away file: " + out)
        self.assertEqual(rc, 1, out)
        self.assertTrue(any(SUITE in line and "FAIL" in line for line in out.splitlines()), "the refusal does not name the red suite: " + out)
        self.assertEqual(pass_lines(out), [], out)

    def test_the_selector_is_the_bases_so_a_lane_that_empties_it_still_runs_the_red_suite(self):
        """The selector runs from origin/<base>, as the config does. The lane writes tools/lane_select.py to list nothing; the base's
        selector lists the red suite for the lane's src/p.py. The base's list decides, so the lane is refused."""
        self.lane_fixture(listed=[SUITE], suites={SUITE: "fail"}, lane={"src/p.py": "VALUE = 1\n"}, lane_listed=[])
        status = self.lane_status()
        self.assertEqual(status.get("tools/lane_select.py"), "M", "the fixture does not change the selector in the lane")
        self.use_ci_job(PASSING, 0)
        rc, out = self.lint_run("--lane-lint", "7")
        self.assertIn(SUITE, self.suite_names(), "the base's selector did not decide the suites; the lane's own selector did: " + out)
        self.assertEqual(rc, 1, out)
        self.assertTrue(any(SUITE in line and "FAIL" in line for line in out.splitlines()), "the refusal does not name the red suite: " + out)
        self.assertEqual(pass_lines(out), [], out)

    def test_a_selector_that_imports_a_helper_the_install_puts_in_the_checkout_still_names_the_red_suite(self):
        """The profile's install writes node_modules/helper.py into the install folder, which the checkout links as node_modules beside
        the lockfile, as npm ci lays it out. The selector imports that helper from ../node_modules, relative to its own file, and exits
        non-zero without it. The lane changes
        src/p.py, and the selector lists a red suite for it. The install runs before the selector, in the checkout, so the helper loads.
        A select that ran first, from a temp copy of base's script, could not load it: every select would read unknown, and the lint
        would refuse without a FAIL line naming the suite."""
        install = [sys.executable, "-c", "import os; os.makedirs('{deps}/node_modules', exist_ok=True); "
                   "open('{deps}/node_modules/helper.py', 'w').write('LISTED = 1\\n')"]
        self.lane_fixture(listed=[SUITE], suites={SUITE: "fail"}, base_files={"package-lock.json": "{}\n"},
                          helper={"folder": "../node_modules", "module": "helper"}, install=install)
        self.assert_suite_is_selector_only(SUITE)
        self.use_ci_job(PASSING, 0)
        rc, out = self.lint_run("--lane-lint", "7")
        self.assertIn(SUITE, self.suite_names(), "the selected suite did not run, because the selector could not import the helper "
                      "the install puts in the checkout: " + out)
        self.assertEqual(rc, 1, out)
        self.assertTrue(any(SUITE in line and "FAIL" in line for line in out.splitlines()), "the refusal does not name the red suite: " + out)
        self.assertEqual(pass_lines(out), [], out)

    def test_a_lane_that_changes_the_selector_still_runs_the_bases_and_its_relative_import_resolves(self):
        """The lane writes tools/lane_select.py to list nothing. The base's selector imports lib/select_lib.py from ../lib, relative to
        its own file, and lists the red suite for the lane's src/p.py. The base's script decides, and its import must resolve where the
        script runs. A copy of only its tools/ folder has no ../lib: the select would exit non-zero, and the lint would refuse without
        a FAIL line naming the suite."""
        self.lane_fixture(listed=[SUITE], suites={SUITE: "fail"}, lane={"src/p.py": "VALUE = 1\n"}, lane_listed=[],
                          base_files={"lib/select_lib.py": "LOADED = True\n"}, helper={"folder": "../lib", "module": "select_lib"})
        status = self.lane_status()
        self.assertEqual(status.get("tools/lane_select.py"), "M", "the fixture does not change the selector in the lane")
        self.assert_suite_is_selector_only(SUITE)
        self.use_ci_job(PASSING, 0)
        rc, out = self.lint_run("--lane-lint", "7")
        self.assertIn(SUITE, self.suite_names(), "the base's selector did not list the red suite, because it could not import "
                      "lib/select_lib.py from ../lib beside its own file: " + out)
        self.assertEqual(rc, 1, out)
        self.assertTrue(any(SUITE in line and "FAIL" in line for line in out.splitlines()), "the refusal does not name the red suite: " + out)
        self.assertEqual(pass_lines(out), [], out)

    def test_an_unreadable_base_config_refuses_the_lane_and_is_not_read_as_no_laneTests(self):
        """The base's config is read with git show, and lane_tests_profile reads a config it cannot read as one that names no laneTests.
        Here origin/main holds a config git reads but that does not parse. The lane is refused, and no suite runs. Every git-show shape
        tried for a missing or unreadable path exits non-zero only when the path is absent, so this is the unreadable shape the case can build."""
        self.lane_fixture(listed=[SUITE], suites={SUITE: "fail"}, laneTests=None, config_text="{not json\n")
        self.use_ci_job(PASSING, 0)
        rc, out = self.run_lane("--lane-lint", "7")
        self.assertNotEqual(rc, 0, "an unreadable base config read as a repo with no laneTests: " + out)
        self.assertEqual(pass_lines(out), [], out)
        self.assertIn("stamp.json", out, "the refusal does not name the unreadable config: " + out)
        self.assertEqual(self.suite_names(), [], "a suite ran on an unreadable base config: " + out)

    def test_every_red_selected_suite_is_named_and_a_green_one_is_not(self):
        listed = [SUITE, OTHER_SUITE, THIRD_SUITE]
        self.lane_fixture(listed=listed, suites={SUITE: "fail", OTHER_SUITE: "fail", THIRD_SUITE: "pass"})
        self.use_ci_job(PASSING, 0)
        rc, out = self.lint_run("--lane-lint", "7")
        self.assertEqual(sorted(self.suite_names()), sorted(listed), "not every selected suite ran at the head: " + out)
        self.assertEqual(rc, 1, out)
        fail_lines = [line for line in out.splitlines() if "FAIL" in line]
        for name in (SUITE, OTHER_SUITE):
            self.assertTrue(any(name in line for line in fail_lines), "the refusal does not name the red suite %s: %s" % (name, out))
        self.assertFalse(any(THIRD_SUITE in line for line in fail_lines), "the refusal names the green suite: " + out)

    def test_an_empty_selection_passes_and_the_pass_line_counts_zero_suites(self):
        self.lane_fixture(listed=[])
        self.use_ci_job(PASSING, 0)
        rc, out = self.lint_run("--lane-lint", "7")
        self.assertEqual(self.suite_names(), [], out)
        self.assertEqual(rc, 0, out)
        lines = pass_lines(out)
        self.assertEqual(len(lines), 1, out)
        self.assertRegex(lines[0], r"\b0 (?:selected )?suites?\b", "the PASS line does not count the zero suites that ran: " + lines[0])

    def test_laneTests_is_a_merge_field_that_the_config_validation_accepts(self):
        tm.put_base_config(self, json.dumps(dict(tm.CONFIG, merge=dict(tm.CONFIG["merge"], laneTests=LANE_PROFILE))))
        try:
            cfg = merge.load_config(self.co, "main", ".github/stamp.json")
        except merge.Stop as error:
            self.fail("the config validation refused merge.laneTests: %s" % error)
        self.assertEqual(cfg["merge"]["laneTests"], LANE_PROFILE)


class ReadyChecks(CiJobStub, tm.RecordsEnv):
    """The ready check of the draft step (merge.draft_step): before a draft goes ready, the repo's declared merge.readyChecks
    run through ci-job as `checks --step NAME ... --base origin/<base>`, on the tree that would be pushed. A FAIL or an
    unknown stops the draft: nothing pushed, no ready mark, and no unknown-ok flag. The stub logs each run. Each red case
    asserts that run first, so a missing check fails there by name. On main a declared key is refused as an unknown field
    before the draft step runs, so the red cases never reach the draft step on main."""

    def setUp(self):
        with unittest.mock.patch.object(tempfile, "tempdir", RUN_FOLDER):  # Env.setUp makes its repos in the temp dir: keep them in this run's folder
            super().setUp()
        self.use_fake_records()
        self.init_stub()

    def declare(self, names, stamp_kinds=False):
        """Put the base's stamp on main with merge.readyChecks `names` (None: no key). Stamp kinds stay off, so no claim,
        unless stamp_kinds gives the repo's own kinds: a claim head needs its pending record."""
        block = dict(tm.CONFIG["merge"])
        if names is not None:
            block["readyChecks"] = names
        kinds = tm.CONFIG["kinds"] if stamp_kinds else []
        tm.put_base_config(self, json.dumps(dict(tm.CONFIG, kinds=kinds, merge=block)))

    def stale_feat(self):
        """feat carries a debt its page does not list, so a draft run rebuilds the page and would push it."""
        self.on("feat", {"debts/gap-one.md": tm.DEBT_TEXT})

    def base_stamp(self, base, names):
        """A branch `base` on origin, made from main, whose stamp declares `names`. The pull request's base becomes it:
        a pull request's config is read from its own base, so the declaration lives there."""
        o = self.other
        tm.sh(o, "git", "fetch", "-q", "origin")
        tm.sh(o, "git", "checkout", "-q", "-B", base, "origin/main")
        tm.put(os.path.join(o, ".github", "stamp.json"), json.dumps(dict(tm.CONFIG, merge=dict(tm.CONFIG["merge"], readyChecks=names))))
        tm.sh(o, "git", "commit", "-qam", f"{base}: declare the ready checks")
        tm.sh(o, "git", "push", "-q", "origin", base)
        self.host.base = base

    def test_a_declared_step_that_fails_stops_the_draft_before_any_push_or_ready(self):
        self.declare(["check invariants"])
        self.stale_feat()
        self.use_ci_job([("FAIL", "check invariants")], 1)
        refs_before = self.refs()
        rc, out = self.draft_confirm()
        self.assertEqual(len(self.lint_calls()), 1, "the ready check did not run the declared step once: " + out)
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.refs(), refs_before, "a page was pushed on a red ready check")
        self.assertEqual(self.host.readies, [], "the pull request went ready on a red ready check")
        self.assertNotIn("ready after its draft run shows", out)

    def test_declared_steps_that_pass_run_ci_job_once_on_the_tree_pushed_and_mark_ready(self):
        names = ["check invariants", "records page"]  # two steps, one run
        self.declare(names)
        self.stale_feat()
        self.use_ci_job([("PASS", name) for name in names], 0)
        before = self.head()
        rc, out = self.draft_confirm()
        runs = self.lint_calls()
        self.assertEqual(len(runs), 1, "the ready check ran ci-job %d times, want once: %s" % (len(runs), out))
        self.assertNotEqual(runs[0]["head"], before, "the check ran on the old head, not on the page commit it would push")
        argv = runs[0]["argv"]
        self.assertEqual(argv[:1], ["checks"], out)
        self.assertNotIn("--lint", argv, out)
        self.assertEqual([argv[i + 1] for i, arg in enumerate(argv) if arg == "--step"], names, out)
        self.assertIn("--base", argv, out)
        self.assertEqual(argv[argv.index("--base") + 1], "origin/main", out)
        self.assertEqual(runs[0]["head"], self.head(), "the ready check ran on a tree other than the one pushed")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.host.readies, [7], out)
        self.assertEqual(self.show("feat", merge.RECORDS_PAGE), tm.page("gap-one").strip())

    def test_a_declared_step_that_passes_on_a_current_page_runs_ci_job_on_the_pr_head(self):
        self.declare(["check invariants"])
        self.on("feat", {merge.RECORDS_PAGE: tm.page()})  # the page is current: nothing to rebuild or push
        self.use_ci_job([("PASS", "check invariants")], 0)
        before = self.head()
        rc, out = self.draft_confirm()
        runs = self.lint_calls()
        self.assertEqual(len(runs), 1, "the ready check ran ci-job %d times, want once: %s" % (len(runs), out))
        self.assertEqual(runs[0]["head"], before, "the ready check ran on a tree other than the PR head")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.host.readies, [7], out)

    def test_a_declared_name_with_no_step_refuses_as_unknown_with_no_unknown_ok_escape(self):
        self.declare(["no such step"])
        self.stale_feat()
        self.use_ci_job([("unknown", "no such step")], 2)
        refs_before = self.refs()
        rc, out = self.draft_confirm()
        self.assertEqual(len(self.lint_calls()), 1, "the declared name did not reach ci-job: " + out)
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.refs(), refs_before, "a page was pushed on an unknown ready check")
        self.assertEqual(self.host.readies, [], "the pull request went ready on an unknown ready check")
        self.assertNotIn("--lint-unknown-ok", out, "the ready check offers the lint's unknown-ok flag")
        self.assertNotIn("ready after its draft run shows", out)

    def test_a_declared_step_that_fails_on_a_non_default_base_still_stops_the_draft(self):
        self.base_stamp("integ", ["check invariants"])
        self.use_ci_job([("FAIL", "check invariants")], 1)
        rc, out = self.draft_confirm()
        runs = self.lint_calls()
        self.assertEqual(len(runs), 1, "the ready check did not run on a non-default base: " + out)
        self.assertIn("--base", runs[0]["argv"], out)
        self.assertEqual(runs[0]["argv"][runs[0]["argv"].index("--base") + 1], "origin/integ", out)
        self.assertEqual(runs[0]["head"], self.head("feat"), "the ready check ran on a tree other than the PR head")
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.host.readies, [], out)

    def test_a_record_claim_head_that_fails_its_declared_step_gets_no_ready_by_hand_remedy(self):
        self.declare(["check invariants"], stamp_kinds=True)  # the config first: a merge after the claim would hide its trailer
        self.claim_head()
        self.assertEqual(self.log1("%(trailers:key=Record-claim,valueonly)", "origin/feat").strip(), "D-002")  # precondition: a claim head
        self.use_ci_job([("FAIL", "check invariants")], 1)
        refs_before = self.refs()
        rc, out = self.draft_confirm()
        self.assertEqual(len(self.lint_calls()), 1, "the Record-claim head's ready check did not run: " + out)
        self.assertNotIn("ready by hand", out)
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.refs(), refs_before, "a push on a red ready check")
        self.assertEqual(self.host.readies, [], out)

    def test_a_record_claim_head_with_no_declared_ready_check_keeps_the_manual_ready_remedy(self):  # the control
        self.claim_head()  # the seed's own stamp: stamp kinds on, no ready checks declared
        self.use_ci_job([("PASS", "check invariants")], 0)
        refs_before = self.refs()
        rc, out = self.draft_confirm()
        self.assertEqual(self.lint_calls(), [], "ci-job ran with no ready checks declared")
        self.assertIn("ready by hand", out)
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.refs(), refs_before, out)
        self.assertEqual(self.host.readies, [], out)

    def test_a_repo_that_declares_no_ready_checks_marks_ready_and_runs_no_ci_job(self):  # the control
        self.declare(None)
        self.stale_feat()
        self.use_ci_job([("PASS", "check invariants")], 0)
        rc, out = self.draft_confirm()
        self.assertEqual(self.lint_calls(), [], "ci-job ran with no ready checks declared")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.host.readies, [7], out)

    def test_a_repo_that_declares_no_ready_checks_says_so_in_one_line(self):
        self.declare(None)
        self.stale_feat()
        self.use_ci_job([("PASS", "check invariants")], 0)
        rc, out = self.draft_confirm()
        notes = [line for line in out.splitlines() if "declares no ready checks" in line.lower()]
        self.assertEqual(len(notes), 1, out)
        self.assertEqual(rc, 0, out)


class RunFolderSweep(unittest.TestCase):
    def test_an_old_sibling_run_folder_goes_and_a_new_one_stays(self):
        root = os.path.join(RUN_FOLDER, "sweep-root")
        os.makedirs(root)
        old = os.path.join(root, "4242-" + uuid.uuid4().hex)
        new = os.path.join(root, "4343-" + uuid.uuid4().hex)
        os.makedirs(old)
        os.makedirs(new)
        two_days_ago = time.time() - 2 * 24 * 60 * 60
        os.utime(old, (two_days_ago, two_days_ago))
        own = _test_temp.run_folder(root)
        self.assertFalse(os.path.exists(old), "the sweep kept a run folder two days old")
        self.assertTrue(os.path.isdir(new), "the sweep removed a run folder made now")
        self.assertTrue(os.path.isdir(own))


if __name__ == "__main__":
    unittest.main()
