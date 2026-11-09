#!/usr/bin/env python3
"""Suite for `merge --lane-lint`: the lint a lane passes before it joins a batch (lanes-run-no-full-ci-job).

Run: python3 merge/test_lane_lint.py
The lint is bin/ci-job's `checks --lint`, reached through merge.CI_JOB. Each case points CI_JOB at a stub that
prints scripted step lines and exits with a scripted code, so no real lint runs. The stub logs each call, so a
case reads what the tool ran, in which tree, at which head. The repo builder, the fakes and the cloud-session
fixture come from merge/test_merge.py: a case extends that fixture, it does not copy it. The draft step's ready check
(class ReadyChecks) runs the same stub, through CiJobStub.
The SIGTERM case runs merge in a subprocess through HARNESS, which names the same stub; it is the one case that does not patch CI_JOB.
BatchLintFlags runs the real bin/ci-job through merge.lane_lint on a batch's four checks.yml lint CI steps, each script logged once with its argv; cost per case: one ci-job copy and run, one worktree, four CI step runs, 0.5 s measured (3 runs of 2 cases). Its two lint-set cases (no lint step; a step that runs only off a pull request) run the same way with their own checks job.
Temp files: this run's folder (lint/_test_temp.py), removed at exit.
"""
import ast, atexit, contextlib, io, json, os, re, shlex, shutil, signal, subprocess, sys, tempfile, time, unittest, unittest.mock, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.append(os.path.join(os.path.dirname(HERE), "lint"))  # append: no lint module shadows one this suite imports
sys.path.append(os.path.join(os.path.dirname(HERE), "hooks"))  # append: the pin note's names (hooks/pin_note.py)
sys.path.append(os.path.join(os.path.dirname(HERE), "testing"))  # append: no testing module shadows one this suite imports
import _test_temp  # noqa: E402  test-temp-standard: this run's folder (lint/_test_temp.py)
import test_merge as tm  # noqa: E402  the git half's fixture and fakes; importing it runs none of its cases
import merge  # noqa: E402
import shallow_clone  # noqa: E402  the one shallow-clone fixture (testing/shallow_clone.py)
from pin_note import MARKER as PIN_NOTE_MARKER  # noqa: E402  the one home of the pin note's marker (hooks/pin_note.py)
from workflow_steps import job_block, run_body, step_blocks, step_env, step_key, step_with  # noqa: E402  the one home of the step parser

RUN_FOLDER = _test_temp.run_folder()
atexit.register(shutil.rmtree, RUN_FOLDER, True)

PASSING = [("PASS", "record slugs"), ("PASS", "ste lint")]
FAILING = [("PASS", "record slugs"), ("FAIL", "comment narration")]
UNKNOWN = [("PASS", "record slugs"), ("unknown", "shellcheck")]
# The drift line bin/ste-changed prints under the pin note's variable: PIN_NOTE_MARKER, then this text.
PIN_NOTE_DRIFT = ("CI pins ste-lint at abc1234 (2026-10-01, .github/workflows/checks.yml:5), older than this copy's lint. "
                  "A line can pass here and fail CI. Move the pin to claude-settings main, in a lane of its own.")

STUB = '''import json, os, subprocess, sys, time
LOG, STEPS, RC, STEP_LOG, SLEEP, PARENT = __LOG__, __STEPS__, __RC__, __STEP_LOG__, __SLEEP__, os.getppid()
DETAILS = __DETAILS__  # step name -> the text after its verdict word; a step not named here reads `stub step`
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
lines = ["%-15s %s: %s" % (state, name, DETAILS.get(name, "stub step")) for state, name in STEPS]
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

    def write_stub(self, steps, rc, sleep=0, details=None):
        """Write the stub ci-job: it prints `steps` ((state, step name) pairs), exits with `rc`, and runs `sleep` s first when it is set.
        `details` maps a step name to the text its line prints after the verdict word (default `stub step`)."""
        text = STUB.replace("__STEP_LOG__", repr(self.step_log)).replace("__LOG__", repr(self.log))
        tm.put(self.stub, text.replace("__STEPS__", repr(steps)).replace("__RC__", repr(rc)).replace("__SLEEP__", repr(sleep))
               .replace("__DETAILS__", repr(details or {})))
        return self.stub

    def use_ci_job(self, steps, rc, details=None):
        """merge.CI_JOB becomes a stub that prints `steps` ((state, step name) pairs) and exits with `rc`."""
        self.write_stub(steps, rc, details=details)
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


class LaneFixture(CiJobStub, tm.CloudSession):
    """The lane-lint fixture: the repo pair, the stub ci-job and the run helpers. LaneLint and CrossMeasure share it."""
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


class LaneLint(LaneFixture):
    """The lane-lint cases: the lint's verdicts, the stack check, the shallow reads and the ref targets."""

    def progress_run(self, steps, rc, *argv):
        """Run merge in a subprocess through HARNESS, with the stub of `steps` (see PROGRESS). -> (rc, stdout, stderr).
        stderr is read live: the case creates the GO file at the first `start:` line, so a stderr that merge captures
        instead of passing on reads to the end only after the stub's bound."""
        go = os.path.join(self.t, "go")
        text = STUB.replace("__STEP_LOG__", repr(self.step_log)).replace("__LOG__", repr(self.log))
        text = text.replace("__STEPS__", repr(steps)).replace("__RC__", repr(rc)).replace("__SLEEP__", repr(0)).replace("__DETAILS__", "{}")
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

    def test_a_passing_lint_with_a_stale_pin_prints_the_whole_drift_line_on_its_pass_line(self):
        self.use_ci_job(PASSING, 0, details={"ste lint": PIN_NOTE_MARKER + PIN_NOTE_DRIFT})
        rc, out = self.lint_run("--lane-lint", "7")
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(pass_lines(out)), 1, out)
        self.assertIn(PIN_NOTE_MARKER + PIN_NOTE_DRIFT, out, "the PASS line lacks the whole drift line: " + out)

    def test_a_passing_lint_with_no_stale_pin_prints_no_pin_note(self):  # the control
        self.use_ci_job(PASSING, 0)
        rc, out = self.lint_run("--lane-lint", "7")
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(pass_lines(out)), 1, out)
        self.assertNotIn(PIN_NOTE_MARKER, out, "a pass with no drift printed a pin note: " + out)

    def test_a_passing_lint_names_its_skipped_ci_steps_on_the_pass_line(self):
        self.use_ci_job(PASSING + [("skipped", "Push-only lint A"), ("skipped", "Push-only lint B")], 0)
        rc, out = self.lint_run("--lane-lint", "7")
        self.assertEqual(rc, 0, out)
        lines = pass_lines(out)
        self.assertEqual(len(lines), 1, out)
        self.assertIn("Push-only lint A", lines[0], out)
        self.assertIn("Push-only lint B", lines[0], out)
        self.assertRegex(lines[0], r"\b2\b", out)

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

    def stacked_pr_on_release(self):
        """PR 7 is feat, based on release, not main. release moves one commit on after feat forked from it. -> (feat sha, release sha)."""
        self.push_release_branch()
        self.host.base = "release"
        o = self.other
        tm.sh(o, "git", "fetch", "-q", "origin")
        tm.sh(o, "git", "checkout", "-q", "-B", "release", "origin/release")
        tm.put(os.path.join(o, "release-moved.txt"), "release moved after feat forked\n")
        tm.sh(o, "git", "add", "-A")
        tm.sh(o, "git", "commit", "-q", "-m", "release moves on")
        tm.sh(o, "git", "push", "-q", "origin", "release")
        return self.head("feat"), tm.sh(o, "git", "rev-parse", "HEAD")

    def contains(self, head, base):
        """True when `base` is an ancestor of `head`. Read in the second clone, which made both commits, so the lane checkout
        is not fetched here: the lint must fetch its own base."""
        return subprocess.run(["git", "-C", self.other, "merge-base", "--is-ancestor", base, head], capture_output=True).returncode == 0

    def merge_release_into_feat(self):
        """The stacked head merges its base in and is pushed. -> the new head sha."""
        o = self.other
        tm.sh(o, "git", "checkout", "-q", "-B", "feat", "origin/feat")
        tm.sh(o, "git", "merge", "-q", "--no-ff", "-m", "merge release into feat", "origin/release")
        tm.sh(o, "git", "push", "-q", "origin", "feat")
        return self.head("feat")

    def shallow_lane_checkout(self, pin):
        """self.co becomes a shallow clone of origin with `pin` fetched at depth 1 (testing/shallow_clone.py, the one fixture).
        The host reads the same checkout, so its root moves with it."""
        self.co = os.path.join(self.t, "shallow")
        error = shallow_clone.make(self.bare, self.co, pin)
        if error:
            self.fail("the shallow clone could not be built: " + error)
        self.host.root = self.co

    def test_a_stacked_pr_whose_head_lacks_its_bases_head_fails_and_names_the_base_its_missing_sha_and_the_merge_commit_remedy(self):
        """The incident: a stacked pull request that lacked its base's head conflicted at merge. The lint passes here, so the
        refusal comes from the stack check alone."""
        feat, release = self.stacked_pr_on_release()
        self.assertFalse(self.contains(feat, release), "precondition: the head already holds the base's head, so the case probes nothing")
        self.use_ci_job(PASSING, 0)
        before = self.refs()
        rc, out = self.run_lane("--lane-lint", "7")
        self.assertEqual(rc, 1, "a stacked PR whose head lacks its base's head did not refuse: " + out)
        self.assertEqual(self.lint_calls(), [], "the ci-job lint ran before the stack check refused: " + out)
        self.assertEqual(pass_lines(out), [], "a stacked PR whose head lacks its base's head printed a PASS line: " + out)
        self.assertIn("release", out, "the refusal does not name the base branch: " + out)
        self.assertIn(release[:7], out, "the refusal does not name the base's missing sha: " + out)
        self.assertRegex(out, r"(?i)merge commit", "the refusal lacks the merge-commit remedy: " + out)
        self.assertEqual(self.refs(), before, "a refused lane pushed a ref")
        self.assertEqual(self.worktrees(), 1, "a refused lane left a worktree behind")

    def test_a_stacked_pr_whose_head_merged_its_base_in_passes_with_the_one_pass_line(self):
        _, release = self.stacked_pr_on_release()
        head = self.merge_release_into_feat()
        self.assertTrue(self.contains(head, release), "precondition: the merge did not bring the base's head into the head")
        self.use_ci_job(PASSING, 0)
        rc, out = self.lint_run("--lane-lint", "7", base="release", head=head)
        self.assertEqual(rc, 0, out)
        lines = pass_lines(out)
        self.assertEqual(len(lines), 1, out)
        self.assertIn(head[:7], lines[0], out)

    def test_a_pr_on_main_whose_head_lacks_mains_head_gets_no_stack_row_and_still_passes(self):
        """Main moving is not this check's job: a PR based on main gets no stack row."""
        self.main_moves()
        new_main = tm.sh(self.other, "git", "rev-parse", "HEAD")
        self.assertFalse(self.contains(self.head("feat"), new_main), "precondition: the head already holds main's head, so the case probes nothing")
        self.use_ci_job(PASSING, 0)
        rc, out = self.lint_run("--lane-lint", "7")
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(pass_lines(out)), 1, out)
        self.assertNotIn(new_main[:7], out, "a PR on main got a stack row that names main's head: " + out)

    def test_the_stack_refusal_is_a_fail_that_no_unknown_ok_reason_lifts(self):
        feat, release = self.stacked_pr_on_release()
        self.assertFalse(self.contains(feat, release), "precondition: the head already holds the base's head, so the case probes nothing")
        self.use_ci_job(UNKNOWN, 2)
        before = self.refs()
        rc, out = self.run_lane("--lane-lint", "7", "--lint-unknown-ok", "shellcheck is not on this box")
        self.assertEqual(rc, 1, "--lint-unknown-ok lifted the stacked PR's refusal: " + out)
        self.assertEqual(pass_lines(out), [], "the stacked PR's refusal printed a PASS line: " + out)
        self.assertRegex(out, r"FAIL", "the stacked PR's refusal does not read as a FAIL: " + out)
        self.assertIn(release[:7], out, "the stacked PR's refusal does not name the base's missing sha: " + out)
        rc, out = self.run_lane("--lane-lint", "7")
        self.assertEqual(rc, 1, "the stacked PR passed without a reason: " + out)
        self.assertRegex(out, r"FAIL", "the stacked PR's refusal without a reason does not read as a FAIL: " + out)
        self.assertIn(release[:7], out, "the stacked PR's refusal without a reason does not name the base's missing sha: " + out)
        self.assertEqual(self.refs(), before, "a refused lane pushed a ref")

    def test_an_unreadable_stack_read_stops_as_unknown_and_no_unknown_ok_reason_lifts_it(self):
        """git could not tell whether the head holds the base's head (merge.ancestor reads None). The stop is unknown: never a FAIL,
        never a PASS, and --lint-unknown-ok does not lift it. The lint does not run."""
        self.stacked_pr_on_release()
        self.use_ci_job(PASSING, 0)
        before = self.refs()
        with unittest.mock.patch.object(merge, "ancestor", return_value=None) as seam:
            rc, out = self.run_lane("--lane-lint", "7", "--lint-unknown-ok", "shellcheck is not on this box")
        self.assertTrue(seam.called, "the stack read did not run, so the case probes nothing")
        self.assertEqual(rc, 1, "--lint-unknown-ok lifted an unreadable stack read: " + out)
        self.assertEqual(pass_lines(out), [], "an unreadable stack read printed a PASS line: " + out)
        self.assertNotRegex(out, r"FAIL", "an unreadable stack read reads as a FAIL: " + out)
        self.assertRegex(out, r"stack check of .* is unknown", "an unreadable stack read does not stop as unknown: " + out)
        self.assertEqual(self.lint_calls(), [], "the lint ran past an unreadable stack read: " + out)
        with unittest.mock.patch.object(merge, "ancestor", return_value=None) as seam:
            rc, out = self.run_lane("--lane-lint", "7")
        self.assertTrue(seam.called, "the stack read did not run on the run without a reason")
        self.assertEqual(rc, 1, "an unreadable stack read passed without a reason: " + out)
        self.assertEqual(pass_lines(out), [], "an unreadable stack read printed a PASS line without a reason: " + out)
        self.assertNotRegex(out, r"FAIL", "an unreadable stack read reads as a FAIL without a reason: " + out)
        self.assertRegex(out, r"stack check of .* is unknown", "an unreadable stack read does not stop as unknown without a reason: " + out)
        self.assertEqual(self.lint_calls(), [], "the lint ran past an unreadable stack read without a reason: " + out)
        self.assertEqual(self.refs(), before, "a refused lane pushed a ref")

    def test_the_stack_refusal_claims_no_conflict_and_no_base_move(self):
        """The head may merge clean, and the lane may never have been based on its base, so the refusal says what is missing and no more."""
        feat, release = self.stacked_pr_on_release()
        self.assertFalse(self.contains(feat, release), "precondition: the head already holds the base's head, so the case probes nothing")
        self.use_ci_job(PASSING, 0)
        rc, out = self.run_lane("--lane-lint", "7")
        self.assertEqual(rc, 1, "a stacked PR whose head lacks its base's head did not refuse: " + out)
        self.assertNotRegex(out, r"(?i)conflict|moved on", "the stack refusal claims a conflict or a base move the lint cannot see: " + out)

    def test_a_shallow_lane_whose_stacked_head_lacks_its_bases_head_fails_and_names_the_base_its_missing_sha_and_the_merge_commit_remedy(self):
        """A shallow clone cuts the path, so `merge-base --is-ancestor` exits 1 and branch_is_ancestor reads unknown. The head lacks the base's
        head in full history (checked on the other clone), so the refusal is a FAIL that names the base, its missing sha and the remedy."""
        feat, release = self.stacked_pr_on_release()
        self.assertFalse(self.contains(feat, release), "precondition: the head already holds the base's head, so the case probes nothing")
        self.shallow_lane_checkout(feat)
        tm.sh(self.co, "git", "fetch", "-q", "origin", "+refs/heads/release:refs/remotes/origin/release")
        facts = shallow_clone.facts(self.co, release, feat)
        self.assertTrue(facts["shallow"], "precondition: the lane checkout is not shallow: " + repr(facts))
        self.assertEqual(facts["ancestor_rc"], 1, "precondition: the cut does not make the read unknown, so the case probes nothing: " + repr(facts))
        self.use_ci_job(PASSING, 0)
        before = self.refs()
        rc, out = self.run_lane("--lane-lint", "7")
        self.assertEqual(rc, 1, "a shallow stacked PR whose head lacks its base's head did not refuse: " + out)
        self.assertEqual(pass_lines(out), [], "a shallow stacked PR whose head lacks its base's head printed a PASS line: " + out)
        self.assertRegex(out, r"FAIL", "a shallow stacked PR whose head lacks its base's head reads as unknown, not a FAIL: " + out)
        self.assertIn(release[:7], out, "the shallow FAIL does not name the base's missing sha: " + out)
        self.assertRegex(out, r"(?i)merge commit", "the shallow FAIL lacks the merge-commit remedy: " + out)
        self.assertEqual(self.refs(), before, "a refused lane pushed a ref")
        self.assertEqual(self.worktrees(), 1, "a refused lane left a worktree behind")

    def test_a_shallow_lane_whose_stacked_head_holds_its_bases_head_passes_at_depth_one(self):
        """The merge commit alone, in a depth-1 clone: its parents are cut, so the stack read must reach past the cut to see the base's
        head. On the current code it reads unknown here. A fix that maps every shallow unknown to a FAIL fails this case too."""
        _, release = self.stacked_pr_on_release()
        head = self.merge_release_into_feat()
        self.shallow_lane_checkout(head)
        tm.sh(self.co, "git", "fetch", "-q", "origin", "+refs/heads/release:refs/remotes/origin/release")
        facts = shallow_clone.facts(self.co, release, head)
        self.assertTrue(facts["shallow"], "precondition: the lane checkout is not shallow: " + repr(facts))
        self.assertTrue(facts["pin_present"], "precondition: the base's head is not in the clone: " + repr(facts))
        self.assertEqual(facts["ancestor_rc"], 1, "precondition: the cut does not hide the base's head, so the case probes nothing: " + repr(facts))
        self.assertTrue(self.contains(head, release), "precondition: the merge did not bring the base's head into the head")
        self.use_ci_job(PASSING, 0)
        rc, out = self.run_lane("--lane-lint", "7")
        self.assertEqual(rc, 0, "a shallow stacked head that holds its base's head reads as unknown, not a pass: " + out)
        self.assertEqual(len(pass_lines(out)), 1, "a shallow stacked head that holds its base's head printed no single PASS line: " + out)
        self.assertEqual(len(self.lint_calls()), 1, "the ci-job lint did not run once on the passing shallow head: " + out)

    def test_a_shallow_lane_whose_stacked_head_holds_its_bases_head_at_depth_two_passes(self):
        """The control beside the depth-1 case: with the merge commit's parents fetched, the path to the base's head is in the clone,
        so the read is an ancestor and the lint passes."""
        _, release = self.stacked_pr_on_release()
        head = self.merge_release_into_feat()
        self.shallow_lane_checkout(head)
        tm.sh(self.co, "git", "fetch", "-q", "--depth", "2", "origin", head)  # the merge commit's parents: the path to the base's head
        tm.sh(self.co, "git", "fetch", "-q", "origin", "+refs/heads/release:refs/remotes/origin/release")
        facts = shallow_clone.facts(self.co, release, head)
        self.assertTrue(facts["shallow"], "precondition: the lane checkout is not shallow: " + repr(facts))
        self.assertEqual(facts["ancestor_rc"], 0, "precondition: the path to the base's head is cut, so the control probes nothing: " + repr(facts))
        self.use_ci_job(PASSING, 0)
        rc, out = self.lint_run("--lane-lint", "7", base="release", head=head)
        self.assertEqual(rc, 0, out)
        lines = pass_lines(out)
        self.assertEqual(len(lines), 1, out)
        self.assertIn(head[:7], lines[0], out)

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


# The stack cross-measure (roadmap step stack-cross-measure): `merge --lane-lint <pr>` checks the PR's head against each other open PR of its
# lane, and against the PRs --with names, with `git merge-tree --write-tree`. The same lane is decided by one rule, in one helper pair
# (session_of, same_lane): the session URL line of the PR body.
OWN = "session_01OwnLaneSeven"  # the session that opened the lane's PR, PR 7
OTHER = "session_01OtherLaneSeven"  # another session's PR
SESSION_URL = "https://claude.ai/code/%s"  # the line a PR body carries for its session


def lane_body(session_id, text="Lane work."):
    """A PR body with its session's URL line, as a lane's PR carries it."""
    return "%s\n\n%s\n" % (text, SESSION_URL % session_id)


def session_of(body):
    """-> the session id a PR body names by its URL line, or None. The one home of the same-lane key: a rule change moves this and same_lane."""
    found = re.search(r"claude\.ai/code/(session_[A-Za-z0-9]+)", body or "")
    return found.group(1) if found else None


def same_lane(body, other):
    """True when two PR bodies name the same session. The cases use it for their preconditions; merge.py holds the rule."""
    mine = session_of(body)
    return mine is not None and mine == session_of(other)


def branch_of(n):
    """The branch a case pushes for PR n. Letters only, so no PR number shows up in a branch name."""
    return "lane-" + str(n).translate(str.maketrans("0123456789", "abcdefghij"))


def names_pr(text, number):
    """True when `text` names PR `number`, as #N or as a bare N. A hex run, such as a commit's sha, never counts."""
    return re.search(r"(?<![0-9a-f])#?%d(?![0-9a-f])" % number, text) is not None


def lane_lint_usage():
    """-> the `merge --lane-lint` entry of merge.py's usage text (its module docstring), from its first line to the next entry. None when absent."""
    lines = (merge.__doc__ or "").splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith("  merge --lane-lint")]
    if not starts:
        return None
    end = next((i for i in range(starts[0] + 1, len(lines)) if lines[i].startswith("  merge ")), len(lines))
    return "\n".join(lines[starts[0]:end])


class CrossMeasure(LaneFixture):
    """`merge --lane-lint <pr>` checks the PR's head against each other open PR of its lane and against the PRs --with names: one
    open-PR list read, then one `git merge-tree --write-tree` per checked PR. A conflict FAILs before the ci-job run and names each
    conflicting PR and file. A stack pair is skipped. The counts come from the fake host (FakeHost.pulls, pull_list_reads) and from
    the merge.sh call log (tree_calls)."""

    contains = LaneLint.contains  # the ancestor read the stack cases use: one home, LaneLint's

    def setUp(self):
        super().setUp()
        self.host.body = lane_body(OWN)
        self.host.pulls = {}
        self.tree_reply, self.tree_calls = None, []  # tree_reply: the (rc, text) every merge-tree call returns, when a case sets one
        real_sh = merge.sh

        def log_merge_tree(args, *rest, **kwargs):
            if "merge-tree" in args:
                self.tree_calls.append(list(args))
                if self.tree_reply is not None:
                    return self.tree_reply
            return real_sh(args, *rest, **kwargs)

        patch = unittest.mock.patch.object(merge, "sh", log_merge_tree)
        patch.start()
        self.addCleanup(patch.stop)

    def commit_on(self, name, files, start):
        """Commit `files` ({path: text}) on branch `name`, cut from `start` in the second clone, and push it. -> the commit's sha."""
        o, sh = self.other, tm.sh
        sh(o, "git", "fetch", "-q", "origin")
        sh(o, "git", "checkout", "-q", "-B", name, start)
        for path, text in files.items():
            tm.put(os.path.join(o, path), text)
        sh(o, "git", "add", "-A")
        sh(o, "git", "commit", "-q", "-m", "%s: %s" % (name, ", ".join(sorted(files))))
        sh(o, "git", "push", "-q", "origin", name)
        return sh(o, "git", "rev-parse", "HEAD")

    def own_writes(self, files):
        """The lane's head gains a commit with `files`. -> its sha."""
        return self.commit_on("feat", files, "origin/feat")

    def listing(self, n, head, body, state="open", draft=False):
        """PR n on `head` with `body`, as the fake host's open-PR list and its PR read carry it. -> the head."""
        self.host.pulls[n] = tm.REST.list_item(n, head, branch_of(n), "main", body=body, draft=draft, state=state)
        return head

    def list_pr(self, n, head, body, state="open", draft=False):
        """PR n on the existing commit `head`: its branch is pushed, so the lane can fetch it, and then it is listed."""
        tm.sh(self.other, "git", "push", "-q", "origin", "%s:refs/heads/%s" % (head, branch_of(n)))
        return self.listing(n, head, body, state=state, draft=draft)

    def pr_writes(self, n, files, body, start="origin/main", state="open", draft=False):
        """PR n: a commit with `files`, cut from `start`, listed as PR n. -> its head sha."""
        head = self.commit_on(branch_of(n), files, start)
        return self.listing(n, head, body, state=state, draft=draft)

    def measured(self, *argv):
        """Run merge in the lane checkout, cloud off, with the counters reset. -> (rc, text, lint runs, PR-list reads, merge-tree calls).
        A refused flag reads as its rc and text (no argparse guard), so each case asserts the outcome, not the parser."""
        if os.path.exists(self.log):
            os.remove(self.log)
        self.host.pull_list_reads = 0
        self.tree_calls.clear()
        rc, out, err = self.run_main(*argv, CLAUDE_CODE_REMOTE=None)
        return rc, out + err, len(self.lint_calls()), self.host.pull_list_reads, len(self.tree_calls)

    def cost_lane(self):
        """The cost pins' lane. PR 8 is checked (same lane, disjoint). PR 9 is a stack pair, so it is skipped. PR 10 is another
        session's and conflicts, so it is read only when --with names it."""
        self.own_writes({"own-b.txt": "lane 7\n"})
        self.pr_writes(8, {"elsewhere.txt": "lane 8\n"}, lane_body(OWN))
        stacked = self.pr_writes(9, {"stack.txt": "stacked on this head\n"}, lane_body(OWN), start="origin/feat")
        self.assertTrue(self.contains(stacked, self.head("feat")), "precondition: PR 9 does not contain this head, so it is no stack pair")
        self.pr_writes(10, {"own-b.txt": "lane 10\n"}, lane_body(OTHER))

    def test_a_same_lane_pr_whose_head_conflicts_fails_and_names_its_number_and_file(self):
        self.own_writes({"shared-a.txt": "lane 7\n"})
        self.pr_writes(8, {"shared-a.txt": "lane 8\n"}, lane_body(OWN))
        self.assertTrue(same_lane(self.host.body, self.host.pulls[8]["body"]), "precondition: PR 8 is not in this lane, so the case probes nothing")
        self.use_ci_job(PASSING, 0)
        rc, text, _, _, _ = self.measured("--lane-lint", "7")
        self.assertEqual(rc, 1, "a same-lane PR whose head conflicts with this head did not refuse: " + text)
        self.assertTrue(names_pr(text, 8), "the refusal does not name the conflicting PR #8: " + text)
        self.assertIn("shared-a.txt", text, "the refusal does not name the conflicting file: " + text)
        self.assertRegex(text, r"FAIL", "the refusal does not read as a FAIL: " + text)
        self.assertEqual(pass_lines(text), [], "a conflicting same-lane PR printed a PASS line: " + text)
        self.assertRegex(text, r"(?i)again", "the refusal lacks its remedy: " + text)

    def test_two_conflicting_same_lane_prs_are_both_named_each_with_its_files(self):
        self.own_writes({"shared-a.txt": "lane 7\n", "shared-b.txt": "lane 7\n", "shared-c.txt": "lane 7\n", "shared-d.txt": "lane 7\n"})
        self.pr_writes(8, {"shared-a.txt": "lane 8\n", "shared-b.txt": "lane 8\n"}, lane_body(OWN))
        self.pr_writes(9, {"shared-c.txt": "lane 9\n", "shared-d.txt": "lane 9\n"}, lane_body(OWN))
        self.use_ci_job(PASSING, 0)
        rc, text, _, _, _ = self.measured("--lane-lint", "7")
        self.assertEqual(rc, 1, "two conflicting same-lane PRs did not refuse: " + text)
        for number, files in ((8, ("shared-a.txt", "shared-b.txt")), (9, ("shared-c.txt", "shared-d.txt"))):
            self.assertTrue(names_pr(text, number), "the refusal does not name conflicting PR #%d: %s" % (number, text))
            for name in files:
                self.assertIn(name, text, "the refusal does not name %s, a file of PR #%d: %s" % (name, number, text))

    def test_a_same_lane_pr_with_a_disjoint_change_passes_with_no_row(self):  # control
        self.own_writes({"own-only.txt": "lane 7\n"})
        self.pr_writes(8, {"elsewhere.txt": "lane 8\n"}, lane_body(OWN))
        self.assertTrue(same_lane(self.host.body, self.host.pulls[8]["body"]), "precondition: PR 8 is not in this lane, so the case probes nothing")
        self.use_ci_job(PASSING, 0)
        rc, text, lints, _, _ = self.measured("--lane-lint", "7")
        self.assertEqual(rc, 0, "a disjoint same-lane PR refused the lane: " + text)
        self.assertEqual(len(pass_lines(text)), 1, text)
        self.assertEqual(lints, 1, "the ci-job lint did not run once on the passing lane: " + text)
        self.assertFalse(names_pr(text, 8), "a disjoint same-lane PR got a row: " + text)

    def test_a_pr_of_another_session_is_not_read_as_this_lane_and_passes(self):  # control
        self.own_writes({"shared-a.txt": "lane 7\n"})
        self.pr_writes(8, {"shared-a.txt": "lane 8\n"}, lane_body(OTHER))
        self.assertFalse(same_lane(self.host.body, self.host.pulls[8]["body"]), "precondition: PR 8 is in this lane, so the case probes nothing")
        self.use_ci_job(PASSING, 0)
        rc, text, _, _, _ = self.measured("--lane-lint", "7")
        self.assertEqual(rc, 0, "a conflicting PR of another session refused this lane: " + text)
        self.assertEqual(len(pass_lines(text)), 1, text)
        self.assertFalse(names_pr(text, 8), "a PR of another session is named: " + text)

    def test_a_stack_pair_is_skipped_and_a_conflicting_pr_beside_it_still_fails(self):
        """The stack pair (PR 9 contains this head) is never merge-tree'd. PR 10 conflicts, so the run FAILs naming PR 10 only."""
        self.own_writes({"shared-a.txt": "lane 7\n"})
        stacked = self.pr_writes(9, {"stack.txt": "stacked on this head\n"}, lane_body(OWN), start="origin/feat")
        self.pr_writes(10, {"shared-a.txt": "lane 10\n"}, lane_body(OWN))
        self.assertTrue(self.contains(stacked, self.head("feat")), "precondition: PR 9 does not contain this head, so it is no stack pair")
        self.use_ci_job(PASSING, 0)
        rc, text, lints, _, trees = self.measured("--lane-lint", "7")
        self.assertEqual(rc, 1, "the conflicting PR beside a stack pair did not refuse: " + text)
        self.assertTrue(names_pr(text, 10), "the refusal does not name the conflicting PR #10: " + text)
        self.assertFalse(names_pr(text, 9), "the refusal names the stack pair PR #9, which is skipped: " + text)
        self.assertEqual(trees, 1, "git merge-tree ran %d times, want one (PR #10 alone): the stack pair was read" % trees)
        self.assertEqual(lints, 0, "the ci-job lint ran past the refusal: " + text)

    def test_a_stack_pair_whose_head_lies_behind_this_head_passes_and_reads_the_list_once(self):
        before = self.head("feat")
        self.own_writes({"own-b.txt": "lane 7\n"})
        behind = self.list_pr(9, before, lane_body(OWN))
        self.assertTrue(self.contains(self.head("feat"), behind), "precondition: this head does not contain PR 9's head, so it is no stack pair")
        self.use_ci_job(PASSING, 0)
        rc, text, _, reads, trees = self.measured("--lane-lint", "7")
        self.assertEqual(rc, 0, "a stack pair whose head lies behind this one refused the lane: " + text)
        self.assertEqual(len(pass_lines(text)), 1, text)
        self.assertEqual(reads, 1, "the open PRs were read %d times, want once" % reads)
        self.assertEqual(trees, 0, "git merge-tree ran %d times for a stack pair, want none" % trees)

    def test_with_names_a_pr_of_another_session_and_its_conflict_fails(self):
        self.own_writes({"shared-a.txt": "lane 7\n"})
        self.pr_writes(9, {"shared-a.txt": "lane 9\n"}, lane_body(OTHER))
        self.assertFalse(same_lane(self.host.body, self.host.pulls[9]["body"]), "precondition: PR 9 is in this lane, so --with probes nothing")
        self.use_ci_job(PASSING, 0)
        rc, text, _, _, _ = self.measured("--lane-lint", "7")  # control: without --with, another session's PR is not read
        self.assertEqual(rc, 0, "a PR of another session, not named by --with, refused the lane: " + text)
        rc, text, lints, _, _ = self.measured("--lane-lint", "7", "--with", "9")
        self.assertEqual(rc, 1, "--with 9 did not refuse a conflicting PR of another session: " + text)
        self.assertTrue(names_pr(text, 9), "the refusal does not name the --with PR #9: " + text)
        self.assertIn("shared-a.txt", text, "the refusal does not name the conflicting file: " + text)
        self.assertEqual(lints, 0, "the ci-job lint ran past the --with refusal: " + text)

    def test_with_names_a_pr_that_does_not_exist_and_stops_unknown(self):
        self.use_ci_job(PASSING, 0)
        rc, text, lints, _, _ = self.measured("--lane-lint", "7", "--with", "99")
        self.assertEqual(rc, 1, "--with 99, a PR that does not exist, did not stop: " + text)
        self.assertTrue(names_pr(text, 99), "the stop does not name PR #99: " + text)
        self.assertRegex(text, r"(?i)unknown|not found|does not exist|no such|404", "the stop does not say it could not read PR #99: " + text)
        self.assertEqual(pass_lines(text), [], "--with of a missing PR printed a PASS line: " + text)
        self.assertEqual(lints, 0, "the ci-job lint ran past the stop: " + text)

    def test_with_names_a_closed_pr_and_stops_unknown(self):
        self.own_writes({"shared-a.txt": "lane 7\n"})
        self.pr_writes(9, {"shared-a.txt": "lane 9\n"}, lane_body(OTHER), state="closed")
        self.use_ci_job(PASSING, 0)
        rc, text, lints, _, _ = self.measured("--lane-lint", "7", "--with", "9")
        self.assertEqual(rc, 1, "--with 9, a closed PR, did not stop: " + text)
        self.assertTrue(names_pr(text, 9), "the stop does not name the closed PR #9: " + text)
        self.assertEqual(pass_lines(text), [], "--with of a closed PR printed a PASS line: " + text)
        self.assertEqual(lints, 0, "the ci-job lint ran past the stop: " + text)

    def test_a_closed_same_lane_pr_is_skipped_and_an_open_one_beside_it_fails(self):
        self.own_writes({"shared-a.txt": "lane 7\n"})
        self.pr_writes(8, {"shared-a.txt": "lane 8\n"}, lane_body(OWN), state="closed")
        self.pr_writes(9, {"shared-a.txt": "lane 9\n"}, lane_body(OWN))
        self.use_ci_job(PASSING, 0)
        rc, text, _, _, _ = self.measured("--lane-lint", "7")
        self.assertEqual(rc, 1, "the open same-lane PR beside a closed one did not refuse: " + text)
        self.assertTrue(names_pr(text, 9), "the refusal does not name the open PR #9: " + text)
        self.assertFalse(names_pr(text, 8), "the refusal names the closed PR #8, which is skipped: " + text)

    def test_a_draft_same_lane_pr_is_still_open_and_its_conflict_fails(self):
        """A draft is an open PR, so the lane's list read counts it. A closed PR beside it is skipped (the case above)."""
        self.own_writes({"shared-a.txt": "lane 7\n"})
        self.pr_writes(8, {"shared-a.txt": "lane 8\n"}, lane_body(OWN), draft=True)
        self.use_ci_job(PASSING, 0)
        rc, text, _, _, _ = self.measured("--lane-lint", "7")
        self.assertEqual(rc, 1, "a conflicting draft of this lane did not refuse: " + text)
        self.assertTrue(names_pr(text, 8), "the refusal does not name the draft PR #8: " + text)

    def test_an_unreadable_merge_tree_stops_unknown_and_no_unknown_ok_reason_lifts_it(self):
        self.pr_writes(8, {"elsewhere.txt": "lane 8\n"}, lane_body(OWN))
        self.tree_reply = (128, "fatal: merge-tree could not read the trees")  # exit 128: neither clean (0) nor conflict (1)
        self.use_ci_job(PASSING, 0)
        rc, text, lints, _, trees = self.measured("--lane-lint", "7")
        self.assertGreater(trees, 0, "git merge-tree was not run, so the case probes nothing")
        self.assertEqual(rc, 1, "an unreadable merge-tree passed the lane: " + text)
        self.assertEqual(pass_lines(text), [], "an unreadable merge-tree printed a PASS line: " + text)
        self.assertRegex(text, r"(?i)unknown", "an unreadable merge-tree does not stop as unknown: " + text)
        self.assertEqual(lints, 0, "the ci-job lint ran past an unreadable merge-tree: " + text)
        rc, text, lints, _, _ = self.measured("--lane-lint", "7", "--lint-unknown-ok", "shellcheck is not on this box")
        self.assertEqual(rc, 1, "--lint-unknown-ok lifted an unreadable merge-tree: " + text)
        self.assertEqual(pass_lines(text), [], "--lint-unknown-ok printed a PASS line for an unreadable merge-tree: " + text)
        self.assertRegex(text, r"(?i)unknown", "--lint-unknown-ok does not leave the unknown stop: " + text)
        self.assertEqual(lints, 0, "the ci-job lint ran past an unreadable merge-tree with a reason: " + text)

    def test_a_conflict_fail_is_never_lifted_by_an_unknown_ok_reason(self):
        self.own_writes({"shared-a.txt": "lane 7\n"})
        self.pr_writes(8, {"shared-a.txt": "lane 8\n"}, lane_body(OWN))
        self.use_ci_job(PASSING, 0)
        rc, text, lints, _, _ = self.measured("--lane-lint", "7", "--lint-unknown-ok", "shellcheck is not on this box")
        self.assertEqual(rc, 1, "--lint-unknown-ok lifted a conflict FAIL: " + text)
        self.assertTrue(names_pr(text, 8), "the refusal does not name conflicting PR #8: " + text)
        self.assertEqual(pass_lines(text), [], "a conflict FAIL printed a PASS line: " + text)
        self.assertEqual(lints, 0, "the ci-job lint ran past a conflict FAIL: " + text)

    def test_with_no_other_open_pr_the_run_reads_the_list_once_and_merge_tree_never(self):  # the empty state
        self.use_ci_job(PASSING, 0)
        rc, text, _, reads, trees = self.measured("--lane-lint", "7")
        self.assertEqual(rc, 0, text)
        self.assertEqual(len(pass_lines(text)), 1, text)
        self.assertEqual(reads, 1, "the open PRs were read %d times with no other PR, want once" % reads)
        self.assertEqual(trees, 0, "git merge-tree ran %d times with no other PR, want none" % trees)

    def test_the_cost_is_one_list_read_and_one_merge_tree_for_each_checked_pr(self):
        self.cost_lane()
        self.use_ci_job(PASSING, 0)
        rc, text, _, reads, trees = self.measured("--lane-lint", "7")
        self.assertEqual(rc, 0, "the cost lane refused, so a PR that is not checked was read: " + text)
        self.assertEqual(reads, 1, "the open PRs were read %d times, want once" % reads)
        self.assertEqual(trees, 1, "git merge-tree ran %d times, want one (PR #8 alone): the stack pair or another session's PR was read" % trees)

    def test_with_adds_one_merge_tree_for_each_named_pr(self):
        self.cost_lane()
        self.use_ci_job(PASSING, 0)
        rc, text, lints, reads, trees = self.measured("--lane-lint", "7", "--with", "10")
        self.assertEqual(rc, 1, "--with 10 did not refuse PR #10's conflict: " + text)
        self.assertTrue(names_pr(text, 10), "the refusal does not name the --with PR #10: " + text)
        self.assertFalse(names_pr(text, 8), "the refusal names PR #8, which does not conflict: " + text)
        self.assertEqual(reads, 1, "the open PRs were read %d times, want once" % reads)
        self.assertEqual(trees, 2, "git merge-tree ran %d times with --with 10, want two (PR #8 and PR #10)" % trees)

    def test_the_usage_text_names_the_cost_of_the_cross_measure(self):
        block = lane_lint_usage()
        self.assertIsNotNone(block, "the usage text has no merge --lane-lint entry")
        self.assertRegex(block, r"merge-tree", "the lane-lint usage does not name git merge-tree as a cost: " + block)
        self.assertRegex(block, r"(?i)(PR|pull[ -]request)[ -]list", "the lane-lint usage does not name the PR-list read as a cost: " + block)
        self.assertRegex(block, r"(?i)per other", "the lane-lint usage does not say merge-tree runs per other PR: " + block)

    def test_a_long_open_list_costs_one_list_read_and_merge_tree_only_for_the_lane(self):  # the full-size state
        self.own_writes({"shared-a.txt": "lane 7\n"})
        head = self.head("feat")
        for n in range(100, 219):  # 119 other sessions' open PRs: none is read
            self.listing(n, head, lane_body(OTHER))
        self.pr_writes(219, {"shared-a.txt": "lane 219\n"}, lane_body(OWN))
        self.use_ci_job(PASSING, 0)
        rc, text, _, reads, trees = self.measured("--lane-lint", "7")
        self.assertEqual(rc, 1, "the conflicting same-lane PR in a long list did not refuse: " + text)
        self.assertTrue(names_pr(text, 219), "the refusal does not name PR #219: " + text)
        self.assertFalse(names_pr(text, 150), "the refusal names another session's PR #150: " + text)
        self.assertEqual(reads, 1, "the open PRs were read %d times in a long list, want once" % reads)
        self.assertEqual(trees, 1, "git merge-tree ran %d times in a long list, want one (PR #219 alone)" % trees)

    def test_the_cross_measure_runs_before_the_ci_job_and_a_fail_never_runs_it(self):
        self.own_writes({"shared-a.txt": "lane 7\n"})
        self.pr_writes(8, {"shared-a.txt": "lane 8\n"}, lane_body(OWN))
        self.use_ci_job(PASSING, 0)  # the stub would pass, so only the cross-measure can stop the lint
        rc, text, lints, _, _ = self.measured("--lane-lint", "7")
        self.assertEqual(rc, 1, "a conflicting same-lane PR did not refuse: " + text)
        self.assertEqual(lints, 0, "the ci-job lint ran although the cross-measure refused: " + text)

    def test_the_usage_text_says_a_pr_under_another_session_id_is_missed_unless_with_names_it(self):
        block = lane_lint_usage()
        self.assertIsNotNone(block, "the usage text has no merge --lane-lint entry")
        self.assertRegex(block, r"(?i)another session[^.]*--with|--with[^.]*another session",
                         "the lane-lint usage does not say a PR posted under another session id is not found unless --with names it: " + block)


BATCH = "batch-lint-flags"  # the batch the case lints: a pushed branch whose checks job holds the four CI steps below
BATCH_MISSING = "batch-lint-flags-no-red-run"  # the same batch with the Red-run trailer's script left out
BASE = "main"  # the base the lint runs against: lane_lint's base, and the PR base the CI steps read
BATCH_CI_STEPS = ("Silent undo check", "Comment narration check", "Red-run trailer", "STE lint")  # checks.yml's job `checks` CI steps this suite lints
STE = "STE lint"  # the one CI step whose script is bin/ste-changed, not a file of the batch
REPO = os.path.dirname(HERE)
CHECKS_YML = os.path.join(REPO, ".github", "workflows", "checks.yml")  # read at test time; no expectation comes from a copy of it
CALL_STUB = "import json, sys\nwith open(%r, 'a', encoding='utf-8') as f:\n    print(json.dumps({'argv': sys.argv}), file=f)\n"  # logs its argv, exits 0
BATCH_NO_LINT = "batch-lint-flags-no-lint"  # a batch whose checks job holds NO_LINT_STEPS: no lint step at all
NO_LINT_STEPS = (("Build", "      - name: Build\n        run: make build\n"),
                 ("Unit tests", "      - name: Unit tests\n        run: python3 -m pytest -q\n"))
BATCH_PUSH_ONLY = "batch-lint-flags-push-only"  # a batch whose checks job adds one lint step that runs only off a pull request
PUSH_ONLY = "Push-only lint"
PUSH_ONLY_STEP = (PUSH_ONLY, "      - name: Push-only lint\n        if: ${{ github.event_name != 'pull_request' }}\n"
                             "        run: python3 lint/check_push_only.py\n")


def real_ci_steps():
    """(name, CI step text) of BATCH_CI_STEPS in checks.yml's checks job, in file order, read by the shared parser."""
    with open(CHECKS_YML, encoding="utf-8") as f:
        block = job_block(f.read(), "checks")
    return [(step_key(st, "name"), st) for st in step_blocks(block) if step_key(st, "name") in BATCH_CI_STEPS]


def workflow_text(found):
    """A workflow of one job, `checks`, holding the given CI step texts in order."""
    return "name: checks\non: pull_request\njobs:\n  checks:\n    runs-on: ubuntu-latest\n    steps:\n" + "".join(text for _, text in found)


def script_of(ci_step):
    """The script a CI step's run: line names, read as its argv reads it, before any env is expanded."""
    return shlex.split(run_body(ci_step).strip())[1]


def github_text(raw, values):
    """The value of one `${{ NAME }}` env value of checks.yml, from `values`: the PR's context as this suite sets it."""
    m = re.fullmatch(r"\$\{\{\s*([\w.]+)\s*\}\}", raw.strip())
    if not m:
        raise AssertionError("checks.yml gives an env value this suite does not read: %r" % raw)
    return values[m.group(1)]


def expected_argv(ci_step, values):
    """The argv checks.yml gives a CI step's run: line, its env: expanded for `values` and split as a shell splits it."""
    env = {name: github_text(raw, values) for name, raw in step_env(ci_step).items()}
    run = run_body(ci_step).strip()
    if "${{" in run:
        raise AssertionError("a run: line of checks.yml holds an expression this suite does not read: %r" % run)
    return shlex.split(re.sub(r"\$(\w+)", lambda m: env[m.group(1)], run))


def gh_eval(expr, inputs):
    """The value of a `${{ }}` of checks.yml made of inputs.NAME, quoted strings, !, && and ||, as GitHub reads those operators."""
    m = re.fullmatch(r"\$\{\{\s*(.*?)\s*\}\}", expr.strip())
    if not m:
        raise AssertionError("checks.yml gives an expression this suite does not read: %r" % expr)
    py = re.sub(r"inputs\.([\w-]+)", lambda x: "INPUTS[%r]" % x.group(1), m.group(1))
    py = re.sub(r"!(?!=)", "not ", py.replace("&&", " and ").replace("||", " or ")).strip()
    tree = ast.parse(py, mode="eval")
    allowed = (ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not, ast.Constant, ast.Subscript, ast.Name, ast.Load)
    for node in ast.walk(tree):
        if not isinstance(node, allowed):
            raise AssertionError("checks.yml gives an expression with %s, which this suite does not read: %r" % (type(node).__name__, expr))
    return eval(compile(tree, "<checks.yml>", "eval"), {"__builtins__": {}}, {"INPUTS": inputs})


def gh_text(value):
    """A GitHub expression's value as the env of a CI step holds it: booleans are the words true and false."""
    return "true" if value is True else "false" if value is False else str(value)


def ste_changed_env(path):
    """{name: constant} of the env dict bin/ste-changed builds for its run, read from its source: the file is parsed, never run. None if absent."""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "dict" and any(k.arg == "SCOPE" for k in node.keywords):
            return {k.arg: k.value.value for k in node.keywords if isinstance(k.value, ast.Constant)}
    return None


def link_or_copy(src, dst):
    """A link at `dst` to `src`, or a copy where the system refuses links (Windows without the symlink right)."""
    try:
        os.symlink(src, dst, target_is_directory=os.path.isdir(src))
    except OSError:
        (shutil.copytree if os.path.isdir(src) else shutil.copy2)(src, dst)


class BatchLintFlags(tm.Env):
    """`merge --lane-lint <batch>` runs the real bin/ci-job on the batch's checks job: each of its four lint CI steps runs once, with the argv checks.yml gives it."""

    def setUp(self):
        with unittest.mock.patch.object(tempfile, "tempdir", RUN_FOLDER):  # Env.setUp makes its repos in the temp dir: keep them in this run's folder
            super().setUp()
        self.found = real_ci_steps()
        self.calls = os.path.join(self.t, "calls")
        os.makedirs(self.calls)
        self.ci_job = self.copy_ci_job()

    def call_log(self, script):
        return os.path.join(self.calls, os.path.basename(script) + ".jsonl")

    def stub_calls(self, script):
        """The logged calls of the stub of `script`, oldest first: empty when it never ran."""
        if not os.path.exists(self.call_log(script)):
            return []
        with open(self.call_log(script), encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def copy_ci_job(self):
        """A copy of bin/ci-job in <t>/ci/bin, with a logging ste-changed beside it: ci-job runs its STE CI step as the file beside its
        own BIN, never the one in the fixture. ci-job imports hooks and lint from the folder above BIN, and runs verdict beside itself."""
        bin_dir = os.path.join(self.t, "ci", "bin")
        os.makedirs(bin_dir)
        shutil.copy2(os.path.join(REPO, "bin", "ci-job"), bin_dir)
        link_or_copy(os.path.join(REPO, "bin", "verdict"), os.path.join(bin_dir, "verdict"))
        for name in ("hooks", "lint"):
            link_or_copy(os.path.join(REPO, name), os.path.join(self.t, "ci", name))
        self.ste_path = os.path.join(bin_dir, "ste-changed")
        tm.put(self.ste_path, "#!/usr/bin/env python3\n" + CALL_STUB % self.call_log("ste-changed"))
        os.chmod(self.ste_path, 0o755)
        return os.path.join(bin_dir, "ci-job")

    def push_batch(self, branch, skip=(), found=None):
        """Push `branch` to origin: one commit on main holding checks.yml's checks job (`found`, else the four lint CI steps) and a
        logging stub for each check script of the four, except the scripts in `skip`. -> the branch's head sha."""
        o = self.other
        tm.sh(o, "git", "fetch", "-q", "origin")
        tm.sh(o, "git", "checkout", "-q", "-B", branch, "origin/" + BASE)
        tm.put(os.path.join(o, ".github", "workflows", "checks.yml"), workflow_text(self.found if found is None else found))
        for name, ci_step in self.found:
            if name != STE and script_of(ci_step) not in skip:
                tm.put(os.path.join(o, script_of(ci_step)), CALL_STUB % self.call_log(script_of(ci_step)))
        tm.sh(o, "git", "add", "-A")
        tm.sh(o, "git", "commit", "-q", "-m", branch + ": the checks job's lint CI steps and their stubs")
        tm.sh(o, "git", "push", "-q", "origin", branch)
        return tm.sh(o, "git", "rev-parse", "HEAD")

    def lane_lint(self, target, out):
        """merge.lane_lint of `target` against BASE, in the lane checkout, through the copy of ci-job. Its output goes to `out`. A refusal raises."""
        env = {"VERDICT_LOG": os.path.join(self.t, "verdict.log")}  # one log for the run: no ci-job log lands in the system temp dir
        with unittest.mock.patch.object(tempfile, "tempdir", RUN_FOLDER), unittest.mock.patch.object(merge, "CI_JOB", self.ci_job), \
                unittest.mock.patch.dict(os.environ, env), contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            return merge.lane_lint(self.co, target, self.host, base=BASE)

    def test_lane_lint_runs_each_batch_check_once_with_the_argv_checks_yml_gives(self):
        head = self.push_batch(BATCH)
        self.assertEqual(sorted(name for name, _ in self.found), sorted(BATCH_CI_STEPS),
                         "checks.yml's checks job does not hold exactly the four CI steps this suite lints")
        out = io.StringIO()
        rc = self.lane_lint(BATCH, out)
        text = out.getvalue()
        self.assertEqual(rc, 0, text)
        self.assertEqual(len(pass_lines(text)), 1, text)
        values = {"github.base_ref": BASE, "github.event.pull_request.head.sha": head}
        for name, ci_step in self.found:
            if name == STE:
                continue
            with self.subTest(check=name):
                want = expected_argv(ci_step, values)
                self.assertEqual(want[0], "python3", "checks.yml's run: of %s is not a python3 line" % name)
                calls = self.stub_calls(want[1])
                self.assertEqual(len(calls), 1, "%s: its script ran %d times, want once: %s" % (name, len(calls), text))
                self.assertEqual(calls[0]["argv"], want[1:], "%s: ran with %s, checks.yml gives %s" % (name, calls[0]["argv"], want[1:]))
        with self.subTest(check=STE):
            calls = self.stub_calls("ste-changed")
            self.assertEqual(len(calls), 1, "STE lint: ste-changed ran %d times, want once: %s" % (len(calls), text))
            argv = calls[0]["argv"]
            self.assertEqual(os.path.realpath(argv[0]), os.path.realpath(self.ste_path),
                             "STE lint ran a ste-changed other than the one beside ci-job")
            self.assertEqual(argv[1:], ["origin/" + BASE], "STE lint: ste-changed got %s, want origin/%s" % (argv[1:], BASE))
            with_ = step_with(dict(self.found)[STE])
            self.assertEqual(sorted(with_), ["fail", "scope"], "checks.yml's STE lint CI step has other with: keys than scope and fail")
            source = ste_changed_env(os.path.join(REPO, "bin", "ste-changed"))
            self.assertIsNotNone(source, "bin/ste-changed builds no env dict with SCOPE")
            inputs = {"full_ste_audit": ""}  # the PR run: the input is empty
            self.assertEqual(source.get("SCOPE"), gh_eval(with_["scope"], inputs),
                             "bin/ste-changed sets SCOPE to other than the PR-path scope of checks.yml")
            self.assertEqual(source.get("FAIL"), gh_text(gh_eval(with_["fail"], inputs)),
                             "bin/ste-changed sets FAIL to other than the PR-path fail of checks.yml")

    def test_a_missing_check_script_refuses_and_never_passes(self):
        red_run = dict(self.found)["Red-run trailer"]
        self.push_batch(BATCH_MISSING, skip={script_of(red_run)})
        out = io.StringIO()
        with self.assertRaises(merge.Stop) as raised:
            self.lane_lint(BATCH_MISSING, out)
        self.assertNotIsInstance(raised.exception, merge.Liftable, "a missing check script reads as unknown, not as a failed check: " + out.getvalue())
        self.assertIn("FAILs:", str(raised.exception), "the refusal does not say the lint FAILs: " + out.getvalue())
        self.assertIn("Red-run trailer", str(raised.exception), "the refusal does not name the CI step whose script is missing: " + out.getvalue())
        self.assertEqual(pass_lines(out.getvalue()), [], "a lint with a check script missing read as a pass: " + out.getvalue())

    def test_a_batch_whose_checks_job_runs_no_lint_step_refuses_as_unknown_and_never_passes(self):
        self.push_batch(BATCH_NO_LINT, found=NO_LINT_STEPS)
        root = tempfile.mkdtemp(prefix="lint-steps-", dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, root, True)
        tm.put(os.path.join(root, ".github", "workflows", "checks.yml"), workflow_text(NO_LINT_STEPS))
        plan = subprocess.run([sys.executable, merge.CI_JOB, "checks", "--lint", "--plan", "--base", "origin/" + BASE],
                              cwd=root, capture_output=True, text=True)  # the exit code is not read: a zero-step plan may exit 2
        self.assertEqual([ln for ln in plan.stdout.splitlines() if ln.startswith("would run ")], [],
                         "the checks job of the batch holds a lint step: " + plan.stdout)  # the scope
        out = io.StringIO()
        with self.assertRaises(merge.Liftable) as raised:
            self.lane_lint(BATCH_NO_LINT, out)
        self.assertIn("no lint CI step ran", str(raised.exception), out.getvalue())
        self.assertEqual(pass_lines(out.getvalue()), [], "a lint run that picked no lint step read as a pass: " + out.getvalue())

    def test_a_lint_step_that_runs_only_off_a_pull_request_is_named_on_the_pass_line(self):
        self.push_batch(BATCH_PUSH_ONLY, found=self.found + [PUSH_ONLY_STEP])
        out = io.StringIO()
        rc = self.lane_lint(BATCH_PUSH_ONLY, out)
        text = out.getvalue()
        self.assertEqual(rc, 0, text)
        lines = pass_lines(text)
        self.assertEqual(len(lines), 1, text)
        self.assertIn(PUSH_ONLY, lines[0], text)


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
