#!/usr/bin/env python3
"""Suite for `merge --lane-lint`: the lint a lane passes before it joins a batch (lanes-run-no-full-ci-job).

Run: python3 merge/test_lane_lint.py
The lint is bin/ci-job's `checks --lint`, reached through merge.CI_JOB. Each case points CI_JOB at a stub that
prints scripted step lines and exits with a scripted code, so no real lint runs. The stub logs each call, so a
case reads what the tool ran, in which tree, at which head, and the env it saw. The stub (CiJobStub, STUB and the
scripts PASSING, FAILING, UNKNOWN) and the repo builder, the fakes and the cloud-session fixture come from merge/test_merge.py:
a case extends that fixture, it does not copy it. The draft step's ready check (class ReadyChecks) runs the same stub.
The review record's lint (class ReviewRecordLint) runs it through ReviewEnv, which passes by default.
The SIGTERM case runs merge in a subprocess through HARNESS, which names the same stub; it is the one case that does not patch CI_JOB.
Temp files: this run's folder (lint/_test_temp.py), removed at exit.
"""
import atexit, json, os, re, shutil, signal, subprocess, sys, tempfile, time, unittest, unittest.mock, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.append(os.path.join(os.path.dirname(HERE), "lint"))  # append: no lint module shadows one this suite imports
import _test_temp  # noqa: E402  test-temp-standard: this run's folder (lint/_test_temp.py)
import test_merge as tm  # noqa: E402  the git half's fixture and fakes; importing it runs none of its cases
import merge  # noqa: E402

RUN_FOLDER = _test_temp.run_folder()
atexit.register(shutil.rmtree, RUN_FOLDER, True)

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


CiJobStub = tm.CiJobStub  # the stub's one home is merge/test_merge.py
PASSING, FAILING, UNKNOWN, STUB = tm.PASSING, tm.FAILING, tm.UNKNOWN, tm.STUB

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
        self.clear_lint_log()
        rc, text = self.run_lane(*argv, cloud=cloud)
        self.assert_one_lint_run(base, head, text)
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


NO_RECORD_PRINTED = re.compile(r"(?i)no (review )?record\b[^\n]*\bprinted")  # a refusal that says the record was not printed
NO_LINT_LINE = re.compile(r"(?i)\bno lint\b|\bnot linted\b|\blint\b[^\n]{0,60}\bnot run\b")  # a stderr line that says no lint ran
NO_JOB_REASON = re.compile(r"(?i)\bchecks\b[^\n]{0,60}\bjob\b")  # the reason, when the workflow has no checks job
NO_FILE_REASON = re.compile(r"(?i)checks\.yml|\bworkflow\b")  # the reason, when the head tree has no workflow file


class ReviewRecordLint(tm.ReviewEnv):
    """`merge <pr> --review-record` runs the lane lint on the reviewed head, after the state, head and fix-check refusals, and prints the
    record only on a PASS (decision pr-review-record). The lint is `checks --lint --base origin/<base>` in a detached tree at the head, and
    the record flag takes no --lint-unknown-ok. Each case that expects a lint run asserts that it ran once before it asserts the result, so a
    record that never lints fails there by name.

    The feature head carries a checks workflow with a checks job (setUp), as a repo that lints on the record does. The stub ignores the tree,
    so only a case that builds the tree shows what the record reads: (a) commits a tree with no workflow file, and (b) one with no checks job."""

    def setUp(self):
        with unittest.mock.patch.object(tempfile, "tempdir", RUN_FOLDER):  # Env.setUp makes its repos in the temp dir: keep them in this run's folder
            super().setUp()
        self.set_feat_workflow(tm.workflow_text("checks", "checks"))

    def set_feat_workflow(self, text):
        """Commit on feat and push it: its .github/workflows/checks.yml becomes `text`, or is removed when `text` is None. The lane checkout and
        the pull request's live head both read origin's feat, so self.head() and self.flags() follow the new head."""
        o = self.other
        tm.sh(o, "git", "fetch", "-q", "origin")
        tm.sh(o, "git", "checkout", "-q", "-B", "feat", "origin/feat")
        path = os.path.join(o, ".github", "workflows", "checks.yml")
        if text is None:
            os.remove(path)
        else:
            tm.put(path, text)
        tm.sh(o, "git", "add", "-A")
        tm.sh(o, "git", "commit", "-q", "-m", "feat: the workflow the review-record lint case sets")
        tm.sh(o, "git", "push", "-q", "origin", "feat")

    def head_files(self):
        """-> the paths in the feature head's tree."""
        tm.sh(self.co, "git", "fetch", "-q", "origin")
        return tm.sh(self.co, "git", "ls-tree", "-r", "--name-only", "origin/feat").splitlines()

    def head_text(self, path):
        """-> the text of `path` in the feature head's tree."""
        tm.sh(self.co, "git", "fetch", "-q", "origin")
        return tm.sh(self.co, "git", "show", "origin/feat:" + path)

    def assert_record_on_stdout_only(self, out, head):
        """stdout holds the record and nothing else, and the record names `head`."""
        body = tm.posted_body(self, out)
        self.assertEqual(out.strip().splitlines(), body.strip().splitlines(), "stdout holds lines besides the record: " + out)
        self.assertEqual(tm.parse_text(self, body)["head"], head, "the record names another head: " + out)

    def assert_one_no_lint_line(self, err, reason):
        """stderr holds one line that says no lint ran, and that line names the reason."""
        notes = [line for line in err.splitlines() if NO_LINT_LINE.search(line)]
        self.assertEqual(len(notes), 1, "stderr does not say once that no lint ran: " + err)
        self.assertRegex(notes[0], reason, "the line that says no lint ran does not name why: " + notes[0])

    def test_a_failed_lint_refuses_and_prints_no_record(self):
        self.use_ci_job(FAILING, 1)
        rc, out, err = self.run_args("7", "--review-record", *self.flags())
        self.assert_one_lint_run("main", self.head(), out + err)
        self.assertNotEqual(rc, 0, "a FAIL lint read as a pass: " + out + err)
        self.assertNotIn(tm.REVIEW_MARKER, out, "the record was printed on a FAIL lint")
        self.assertIn("comment narration", err, "the refusal does not name the failing step: " + err)
        self.assertRegex(err, NO_RECORD_PRINTED, "the refusal does not say that no record was printed: " + err)

    def test_an_unknown_lint_refuses_and_offers_no_unknown_ok_flag(self):
        self.use_ci_job(UNKNOWN, 2)
        rc, out, err = self.run_args("7", "--review-record", *self.flags())
        self.assert_one_lint_run("main", self.head(), out + err)
        self.assertNotEqual(rc, 0, "an unknown lint read as a pass: " + out + err)
        self.assertNotIn(tm.REVIEW_MARKER, out, "the record was printed on an unknown lint")
        self.assertIn("unknown", err.lower(), "the refusal does not say the lint is unknown: " + err)
        self.assertNotIn("--lint-unknown-ok", err, "the refusal offers --lint-unknown-ok, which --review-record does not take: " + err)

    def test_a_timed_out_lint_refuses_as_unknown_and_prints_no_record(self):
        self.use_ci_job(PASSING, 0, sleep=60)  # the stub outlasts the bound below, so the lint run is killed at the bound
        with unittest.mock.patch.object(merge, "LINT_SECONDS", 3):
            rc, out, err = self.run_args("7", "--review-record", *self.flags())
        self.assert_one_lint_run("main", self.head(), out + err)
        self.assertNotEqual(rc, 0, "a timed-out lint read as a pass: " + out + err)
        self.assertNotIn(tm.REVIEW_MARKER, out, "the record was printed on a timed-out lint")
        self.assertIn("unknown", err.lower(), "the refusal does not say the lint is unknown: " + err)

    def test_a_docs_only_change_lints_once_at_the_reviewed_head_and_prints_the_record(self):
        self.use_ci_job(PASSING, 0)
        head = self.head()
        rc, out, err = self.run_args("7", "--review-record", "--kind", "docs-only", "--guard", "no", "--head", head)
        self.assert_one_lint_run("main", head, out + err)
        self.assertEqual(rc, 0, out + err)
        rec = tm.parse_text(self, tm.posted_body(self, out))
        self.assertEqual((rec["kind"], rec["head"]), ("docs-only", head), out + err)

    def test_a_passing_lint_prints_only_the_record_on_stdout(self):
        # (c), the control for (a) and (b): the feature head holds a checks job, so the lint runs once on it and the record prints.
        self.assertRegex(self.head_text(".github/workflows/checks.yml"), r"(?m)^  checks:", "the precondition: the head workflow has no checks job")
        self.use_ci_job(PASSING, 0)
        rc, out, err = self.run_args("7", "--review-record", *self.flags())
        self.assert_one_lint_run("main", self.head(), out + err)
        self.assertEqual(rc, 0, out + err)
        self.assertEqual(pass_lines(out), [], "a PASS line went to stdout, where the record is parsed from: " + out)
        body = tm.posted_body(self, out)
        self.assertEqual(out.strip().splitlines(), body.strip().splitlines(), "stdout holds lines besides the record: " + out)

    def test_a_head_refusal_runs_no_lint_and_a_matching_head_lints_once(self):
        self.use_ci_job(PASSING, 0)
        old = self.head()
        self.host.head_override = "f" * 40  # the pull request moved on: its live head is not the reviewed one
        rc, out, err = self.run_args("7", "--review-record", *tm.REVIEW_FLAGS, "--head", old)
        self.assertEqual(self.lint_calls(), [], "the head refusal ran the lint: " + out + err)
        self.assertNotEqual(rc, 0, "a head refusal printed a record: " + out + err)
        self.assertIn(old[:9], err, "the refusal does not name the reviewed head: " + err)
        self.assertIn("f" * 9, err, "the refusal does not name the live head: " + err)
        # The control: the same command with the live head at the reviewed head lints once. Main runs no lint, so this half is the red there.
        self.host.head_override = None
        self.clear_lint_log()
        rc, out, err = self.run_args("7", "--review-record", *self.flags())
        self.assert_one_lint_run("main", old, out + err)
        self.assertEqual(rc, 0, out + err)

    def test_the_lint_run_drops_hook_catalog_root_from_its_env(self):
        self.use_ci_job(PASSING, 0)
        with unittest.mock.patch.dict(os.environ, {"HOOK_CATALOG_ROOT": "/some/other/tree", "LINT_STUB_SENTINEL": "kept"}):
            state, lines, _log, _liftable = merge.ci_job_run(self.co, "checks", "--lint", "--base", "origin/main")
        calls = self.lint_calls()
        self.assertEqual(len(calls), 1, "ci_job_run ran the stub %d times, want once" % len(calls))
        seen = calls[0]["env"]
        self.assertEqual(seen["LINT_STUB_SENTINEL"], "kept", "the stub did not see the env ci_job_run passes, so the next line proves nothing")
        self.assertIsNone(seen["HOOK_CATALOG_ROOT"], "the lint saw HOOK_CATALOG_ROOT=%r, so it reads another tree" % seen["HOOK_CATALOG_ROOT"])
        self.assertEqual(state, "pass", "ci_job_run read %r, want pass" % (lines,))

    def test_a_head_with_no_checks_workflow_runs_no_lint_and_says_why_on_one_stderr_line(self):  # (a)
        self.set_feat_workflow(None)
        self.assertNotIn(".github/workflows/checks.yml", self.head_files(), "the precondition: the head tree still holds the workflow file")
        head = self.head()
        rc, out, err = self.run_args("7", "--review-record", *self.flags())
        self.assertEqual(self.lint_calls(), [], "the lint ran %d times, want 0, for a head with no workflow file" % len(self.lint_calls()))
        self.assertEqual(rc, 0, out + err)
        self.assert_record_on_stdout_only(out, head)
        self.assert_one_no_lint_line(err, NO_FILE_REASON)

    def test_a_head_whose_workflow_has_no_checks_job_runs_no_lint_and_says_why_on_one_stderr_line(self):  # (b)
        # The job names are near misses on purpose: a match on the word `checks` alone would read checks-merge-install as the checks job.
        self.set_feat_workflow(tm.workflow_text("checks", "checks-merge-install", "lint"))
        self.assertIn(".github/workflows/checks.yml", self.head_files(), "the precondition: the head tree lacks the workflow file")
        self.assertIsNone(re.search(r"(?m)^  checks:", self.head_text(".github/workflows/checks.yml")), "the precondition: the head workflow has a checks job")
        head = self.head()
        rc, out, err = self.run_args("7", "--review-record", *self.flags())
        self.assertEqual(self.lint_calls(), [], "the lint ran %d times, want 0, for a workflow with no checks job" % len(self.lint_calls()))
        self.assertEqual(rc, 0, out + err)
        self.assert_record_on_stdout_only(out, head)
        self.assert_one_no_lint_line(err, NO_JOB_REASON)


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
