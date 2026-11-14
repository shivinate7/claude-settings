#!/usr/bin/env python3
"""Suite for the per-check bounds of the pre-ready run (roadmap step ready-checks-time-bound).

Run: python3 merge/test_ready_bounds.py

Each ready check of the pre-ready run has a bound of its own. A check that does not finish in its bound reads
`unknown`, never a pass, and its line names the check and the bound:
  READY_CI_STEP_SECONDS  each ci-job step of merge.readyChecks; merge hands it to ci-job as CI_JOB_STEP_SECONDS
  READY_CLASH_SECONDS    the open-PR clash check: all of clash_verdict, its merge read included
  READY_DEBT_SECONDS     the debt-close lint: all of debt_verdict, a hang in Python code included
Each check prints `start: <check> (bound N s)` before it runs, so a run shows which check it is on.

A hang here is a stub that does not finish on its own. Hang waits on an Event for BOUND + 5 s and sets `gave_up` when
that wait ran out. A bounded run returns first, so each case asserts `gave_up` is unset: the case reads no clock.
HungRead runs a real child process that outlives the bound, as a git or gh call with no timeout does, and the case kills it.

Groups: the bound constants exist (red until merge.py names them), each check's bound applies (red), the start lines and
the whole run (red), and controls: a check under its bound keeps its own verdict (green on the old code, which pins what
the bound must keep).
The run bound: ready_ci_run_seconds of the ready checks is past the checks times READY_CI_STEP_SECONDS (red), and one more ready
check moves the bound of its job's ci-job call by READY_CI_STEP_SECONDS (red). The clash read's pools do not hold the process at exit (red, one case per
pool, in a child process). A debt lint that does not load reads unknown, naming the lint (red); `import merge` still works
without it (control).
Temp files: each case's folders come from this run's folder (lint/_test_temp.py), removed at exit.
"""
import contextlib, io, json, os, shutil, signal, subprocess, sys, tempfile, threading, time, unittest, unittest.mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import merge  # noqa: E402
sys.path.append(os.path.join(REPO, "lint"))  # append: no lint module shadows one this suite imports
import _test_temp  # noqa: E402  test-temp-standard: the run folder's one home (lint/_test_temp.py)

RUN_FOLDER = _test_temp.run_folder()
unittest.addModuleCleanup(shutil.rmtree, RUN_FOLDER, True)
BOUND = 3  # seconds: the bound each hang case sets
INFO = {"head": "c" * 40, "body": ""}
with open(os.path.join(REPO, ".github", "stamp.json"), encoding="utf-8") as f:
    READY_CHECKS = json.load(f)["merge"]["readyChecks"]  # read, not copied: the checks the real pre-ready run names


def bound(name, seconds):
    """merge's bound constant set to `seconds` for one case. create=True: on a merge.py without the name, the case reads its
    own assert, not an AttributeError."""
    return unittest.mock.patch.object(merge, name, seconds, create=True)


class Hang:
    """A check that does not finish on its own. It waits `seconds` on `release`, and sets `gave_up` when that wait ran out."""

    def __init__(self, seconds, value=None):
        self.release, self.seconds, self.value = threading.Event(), seconds, value
        self.entered = self.gave_up = False

    def __call__(self, *args, **kwargs):
        self.entered = True
        if not self.release.wait(self.seconds):
            self.gave_up = True
        return self.value


class HungRead:
    """A merge read that runs a real child process for `seconds`, as a git or gh call does when merge.sh has no timeout. The child
    writes its pid to `pid_file` first, so the case can end it."""

    def __init__(self, pid_file, seconds):
        self.pid_file, self.seconds = pid_file, seconds
        self.entered = self.gave_up = False

    def __call__(self, *args, **kwargs):
        self.entered = True
        code = "import os, time\nwith open(%r, 'w') as f:\n    f.write(str(os.getpid()))\ntime.sleep(%d)\n" % (self.pid_file, self.seconds)
        merge.sh([sys.executable, "-c", code])
        self.gave_up = True
        return None


def kill_recorded_child(pid_file):
    """Ends the child a HungRead recorded, if it still runs: a case that leaves it alive would hold its folder open."""
    try:
        with open(pid_file, encoding="utf-8") as f:
            pid = int(f.read())
    except (OSError, ValueError):
        return
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def slow(seconds, value):
    """A check that finishes after `seconds` of work with `value`."""
    def run(*args, **kwargs):
        time.sleep(seconds)
        return value
    return run


def ci_job_passes(checks, calls=None):
    """Stands in for merge.ci_job_run: each check in `checks` passes, and the lines are the ones pre_ready_rows reads. calls, when
    given, receives each call's job and keyword arguments, such as the bound the run was given."""
    def run(wt, *args, raw=None, **kwargs):
        if calls is not None:
            calls.append({"job": args[0], **kwargs})
        if raw is not None:
            raw.extend(f"PASS {name}: ok" for name in checks)
        return "pass", [], [], False
    return run


def fake_sh_ci_job(calls):
    """Stands in for merge.sh: a call that runs bin/ci-job passes every ready check, and each such call is recorded as (argv, kwargs).
    Any other command fails, so no case reaches git or gh."""
    def fake(args, *rest, **kwargs):
        if list(args[1:2]) == [merge.CI_JOB]:
            calls.append((list(args), kwargs))
            return 0, "\n".join(f"PASS {name}: ok" for name in READY_CHECKS)
        return 1, "unexpected command in a pre-ready case: " + " ".join(map(str, args))
    return fake


@contextlib.contextmanager
def ready_world(debt=None, clash=None, merge_reason=None, checks=READY_CHECKS):
    """The reads of the pre-ready run, stubbed. ci-job passes `checks`. debt is debt_check's stub and clash is cross_measure's
    (None: a pass). merge_reason is its stub (None: the head merges clean)."""
    with unittest.mock.patch.object(merge, "ci_job_run", ci_job_passes(checks)), \
            unittest.mock.patch.object(merge, "debt_check", debt if debt is not None else (lambda *a, **k: None)), \
            unittest.mock.patch.object(merge, "merge_reason", merge_reason if merge_reason is not None else (lambda *a, **k: None)), \
            unittest.mock.patch.object(merge, "cross_measure", clash if clash is not None else (lambda *a, **k: ([], [], False))):
        yield


class BoundsExist(unittest.TestCase):
    """Each ready check has a bound constant of its own, and the debt bound is not below the debt lint's own cap."""

    def test_each_ready_check_names_a_positive_bound_in_seconds(self):
        for name in ("READY_CI_STEP_SECONDS", "READY_CLASH_SECONDS", "READY_DEBT_SECONDS"):
            with self.subTest(name=name):
                value = getattr(merge, name, None)
                self.assertIsNotNone(value, f"merge.py names no {name}, so that check has no bound of its own")
                self.assertGreater(value, 0, f"{name} is not a positive number of seconds")

    def test_the_debt_bound_is_not_below_the_debt_lint_cap(self):
        value = getattr(merge, "READY_DEBT_SECONDS", None)
        self.assertIsNotNone(value, "merge.py names no READY_DEBT_SECONDS, so the debt-close lint has no bound at merge level")
        cap = merge.load_debt_retire().TIMEOUT
        self.assertGreaterEqual(value, cap, f"READY_DEBT_SECONDS ({value} s) is below the debt lint's own cap ({cap} s)")

    def run_bound(self):
        """ready_ci_run_seconds of merge.readyChecks, the one home of the whole run's bound. getattr: a missing name reads as this assert."""
        fn = getattr(merge, "ready_ci_run_seconds", None)
        self.assertIsNotNone(fn, "merge.py names no ready_ci_run_seconds, so the whole pre-ready run has no backstop")
        return fn(READY_CHECKS)

    def test_the_run_bound_exceeds_the_ready_checks_times_the_step_bound(self):
        value = self.run_bound()
        floor = len(READY_CHECKS) * merge.READY_CI_STEP_SECONDS
        self.assertGreater(value, floor, f"ready_ci_run_seconds of the ready checks ({value} s) does not exceed {len(READY_CHECKS)} ready checks x "
                                         f"{merge.READY_CI_STEP_SECONDS} s = {floor} s, so the backstop can end the run while a step still has its bound")

    def test_the_run_bound_is_the_ready_checks_times_the_step_bound_plus_300_seconds(self):
        value = self.run_bound()
        want = len(READY_CHECKS) * merge.READY_CI_STEP_SECONDS + 300
        self.assertEqual(value, want, f"ready_ci_run_seconds of the ready checks is {value} s, not {len(READY_CHECKS)} ready checks x "
                                      f"{merge.READY_CI_STEP_SECONDS} s + 300 s = {want} s")


class ClashBound(unittest.TestCase):
    """clash_verdict: a read that outlives READY_CLASH_SECONDS reads unknown, and the bound covers the merge read too."""

    def setUp(self):
        self.root = tempfile.mkdtemp(dir=RUN_FOLDER)

    def test_a_hanging_cross_pr_read_reads_unknown_naming_the_check_and_its_bound(self):
        hang = Hang(BOUND + 5, ([], [], False))
        self.addCleanup(hang.release.set)
        with bound("READY_CLASH_SECONDS", BOUND), \
                unittest.mock.patch.object(merge, "merge_reason", lambda *a, **k: None), \
                unittest.mock.patch.object(merge, "cross_measure", hang), \
                contextlib.redirect_stdout(io.StringIO()):
            verdict, name, detail = merge.clash_verdict(self.root, 7, "main", None, INFO)
        self.assertTrue(hang.entered, "the clash check never reached its cross-PR read, so this case proves nothing")
        self.assertFalse(hang.gave_up, "the clash check ran past its bound + 5 s: it returned only when its own wait ran out")
        self.assertEqual(name, "open-PR clash")
        self.assertEqual(verdict, "unknown", f"a clash check past its bound reads {verdict}, not unknown")
        self.assertIn(f"did not finish in {BOUND} s", detail, f"the unknown text does not name the bound: {detail!r}")

    def test_a_hanging_merge_read_inside_the_clash_check_reads_unknown_within_the_same_bound(self):
        pid_file = os.path.join(self.root, "child.pid")
        self.addCleanup(kill_recorded_child, pid_file)
        hung = HungRead(pid_file, BOUND + 25)
        with bound("READY_CLASH_SECONDS", BOUND), \
                unittest.mock.patch.object(merge, "merge_reason", hung), \
                unittest.mock.patch.object(merge, "cross_measure", lambda *a, **k: ([], [], False)), \
                contextlib.redirect_stdout(io.StringIO()):
            verdict, name, detail = merge.clash_verdict(self.root, 7, "main", None, INFO)
        self.assertTrue(hung.entered, "the merge read never ran, so this case proves nothing")
        self.assertFalse(hung.gave_up, "the merge read of the clash check ran past the clash bound + 5 s")
        self.assertEqual(name, "open-PR clash")
        self.assertEqual(verdict, "unknown", f"a clash check whose merge read hung reads {verdict}, not unknown")
        self.assertIn(f"did not finish in {BOUND} s", detail, f"the unknown text does not name the bound: {detail!r}")


class ClashVerdictsUnderTheBound(unittest.TestCase):
    """Controls: a clash check under its bound keeps its own verdict and its own text. The bound never softens a fail or an unknown,
    and never drops a report from a full list."""

    def setUp(self):
        self.root = tempfile.mkdtemp(dir=RUN_FOLDER)

    def verdict_of(self, cross_measure):
        with bound("READY_CLASH_SECONDS", 10), \
                unittest.mock.patch.object(merge, "merge_reason", lambda *a, **k: None), \
                unittest.mock.patch.object(merge, "cross_measure", cross_measure), \
                contextlib.redirect_stdout(io.StringIO()):
            return merge.clash_verdict(self.root, 7, "main", None, INFO)

    def test_a_clash_read_that_finishes_under_its_bound_passes(self):
        self.assertEqual(self.verdict_of(slow(1, ([], [], False))), ("pass", "open-PR clash", ""))

    def test_a_clash_that_fails_under_the_bound_stays_a_fail(self):
        verdict, name, detail = self.verdict_of(lambda *a, **k: (["#5 and #7 both change a.py"], [], False))
        self.assertEqual((verdict, name), ("fail", "open-PR clash"))
        self.assertIn("#5 and #7 both change a.py", detail)

    def test_an_unknown_read_under_the_bound_stays_unknown(self):
        verdict, name, detail = self.verdict_of(lambda *a, **k: ([], [], "the open PR list could not be read"))
        self.assertEqual((verdict, name), ("unknown", "open-PR clash"))
        self.assertIn("could not be read", detail)

    def test_a_full_report_list_keeps_its_count_and_its_shown_lines(self):
        shown = merge.PRE_READY_REPORT_LINES
        reports = [f"#{i} shares files: a{i}.py" for i in range(shown + 3)]
        verdict, name, detail = self.verdict_of(lambda *a, **k: ([], reports, False))
        self.assertEqual(verdict, "pass")
        self.assertIn(f"{len(reports)} clash(es) not counted", detail)
        self.assertIn("and 3 more clash(es) not counted", detail)


class DebtBound(unittest.TestCase):
    """debt_verdict: a debt lint past READY_DEBT_SECONDS reads unknown, a hang in Python code included."""

    def setUp(self):
        self.wt = tempfile.mkdtemp(dir=RUN_FOLDER)

    def test_a_hanging_debt_lint_reads_unknown_naming_the_check_and_its_bound(self):
        hang = Hang(BOUND + 5)
        self.addCleanup(hang.release.set)
        with bound("READY_DEBT_SECONDS", BOUND), \
                unittest.mock.patch.object(merge, "debt_check", hang), \
                contextlib.redirect_stdout(io.StringIO()):
            verdict, name, detail = merge.debt_verdict(self.wt, "main", None, INFO)
        self.assertTrue(hang.entered, "the debt lint never ran, so this case proves nothing")
        self.assertFalse(hang.gave_up, "the debt lint ran past its bound + 5 s")
        self.assertEqual(name, "debt retire")
        self.assertEqual(verdict, "unknown", f"a debt lint past its bound reads {verdict}, not unknown")
        self.assertIn(f"did not finish in {BOUND} s", detail, f"the unknown text does not name the bound: {detail!r}")

    def test_a_debt_lint_that_finishes_under_its_bound_passes(self):
        with bound("READY_DEBT_SECONDS", 10), \
                unittest.mock.patch.object(merge, "debt_check", slow(1, None)), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(merge.debt_verdict(self.wt, "main", None, INFO), ("pass", "debt retire", ""))

    def test_a_dropped_debt_stays_fail_and_an_unread_one_stays_unknown(self):
        cases = (
            (merge.Dropped("the branch closes a debt without proof\n  x\nDEBT CITE"), "fail"),
            (merge.Unread("the debt-close check could not read the history\nDEBT CITE"), "unknown"),
        )
        for raised, want in cases:
            with self.subTest(verdict=want):
                with bound("READY_DEBT_SECONDS", 10), \
                        unittest.mock.patch.object(merge, "debt_check", side_effect=raised), \
                        contextlib.redirect_stdout(io.StringIO()):
                    verdict, name, _ = merge.debt_verdict(self.wt, "main", None, INFO)
                self.assertEqual((verdict, name), (want, "debt retire"))


class CiStepBound(unittest.TestCase):
    """The pre-ready run hands READY_CI_STEP_SECONDS to ci-job, which reads it as CI_JOB_STEP_SECONDS."""

    def setUp(self):
        self.wt = tempfile.mkdtemp(dir=RUN_FOLDER)

    def test_the_ready_run_hands_each_ci_job_step_its_bound_in_the_environment(self):
        calls = []
        with bound("READY_CI_STEP_SECONDS", 7), \
                unittest.mock.patch.object(merge, "sh", fake_sh_ci_job(calls)), \
                contextlib.redirect_stdout(io.StringIO()):
            merge.pre_ready_rows(self.wt, 7, "main", READY_CHECKS, None)
        self.assertTrue(calls, "the pre-ready run made no ci-job call, so the bound was never handed over")
        _, kwargs = calls[0]
        self.assertEqual(kwargs.get("env", {}).get("CI_JOB_STEP_SECONDS"), "7",
                         "ci-job did not get READY_CI_STEP_SECONDS as CI_JOB_STEP_SECONDS")


class RunLines(unittest.TestCase):
    """pre_ready_rows prints each check's start line, with its bound, before the check runs. A hung clash read ends the run
    within its bound, and its unknown line names the check and the bound."""

    def setUp(self):
        self.root = tempfile.mkdtemp(dir=RUN_FOLDER)
        self.out = io.StringIO()

    def test_the_debt_start_line_with_its_bound_is_printed_before_the_debt_lint_runs(self):
        seen = {}

        def debt(*a, **k):
            seen["entered"] = True
            seen["printed"] = self.out.getvalue().splitlines()
            return None

        with bound("READY_DEBT_SECONDS", BOUND), ready_world(debt=debt), \
                contextlib.redirect_stdout(self.out), contextlib.redirect_stderr(self.out):
            merge.pre_ready_rows(self.root, 7, "main", READY_CHECKS, (self.root, None, INFO))
        self.assertTrue(seen.get("entered"), "the debt lint never ran")
        self.assertIn(f"start: debt retire (bound {BOUND} s)", seen["printed"],
                      "the debt lint ran before its start line was printed")

    def test_the_clash_start_line_with_its_bound_is_printed_before_the_clash_read_runs(self):
        seen = {}

        def clash(*a, **k):
            seen["entered"] = True
            seen["printed"] = self.out.getvalue().splitlines()
            return [], [], False

        with bound("READY_CLASH_SECONDS", BOUND), ready_world(clash=clash), \
                contextlib.redirect_stdout(self.out), contextlib.redirect_stderr(self.out):
            merge.pre_ready_rows(self.root, 7, "main", READY_CHECKS, (self.root, None, INFO))
        self.assertTrue(seen.get("entered"), "the clash read never ran")
        self.assertIn(f"start: open-PR clash (bound {BOUND} s)", seen["printed"],
                      "the clash read ran before its start line was printed")

    def test_a_hanging_clash_returns_the_run_within_its_bound_with_its_unknown_line(self):
        hang = Hang(BOUND + 5, ([], [], False))
        self.addCleanup(hang.release.set)
        with bound("READY_CLASH_SECONDS", BOUND), bound("READY_DEBT_SECONDS", BOUND), ready_world(clash=hang), \
                contextlib.redirect_stdout(self.out), contextlib.redirect_stderr(self.out):
            rows, _ = merge.pre_ready_rows(self.root, 7, "main", READY_CHECKS, (self.root, None, INFO))
        self.assertTrue(hang.entered, "the clash read never ran, so this case proves nothing")
        self.assertEqual([name for _, name, _ in rows], [*READY_CHECKS, "debt retire", "open-PR clash"],
                         "the pre-ready run did not reach every check")
        self.assertFalse(hang.gave_up, "the pre-ready run ran past the clash bound + 5 s")
        self.assertIn(f"unknown open-PR clash: did not finish in {BOUND} s", self.out.getvalue().splitlines(),
                      "the clash line does not name the check and its bound")


class RunBoundFollowsTheChecks(unittest.TestCase):
    """The run bound comes from the checks the run is given: merge.readyChecks in .github/stamp.json, which fast_checks and the draft
    step read and pass to pre_ready_rows as `checks`. One more check moves the bound by READY_CI_STEP_SECONDS."""

    def setUp(self):
        self.root = tempfile.mkdtemp(dir=RUN_FOLDER)

    def bounds_for(self, checks):
        """-> [(job, bound)] of the ci-job calls the pre-ready run makes for `checks`, in call order."""
        calls = []
        with unittest.mock.patch.object(merge, "ci_job_run", ci_job_passes(checks, calls)), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            merge.pre_ready_rows(self.root, 7, "main", checks, None)
        return [(call["job"], call.get("bound")) for call in calls]

    def test_one_more_ready_check_moves_the_run_bound_by_the_step_bound(self):
        extra = "One more check"
        extended = [*READY_CHECKS, extra]
        job = next(j for j, group in merge.ready_job_groups(extended).items() if any(entry == extra for entry, _ in group))
        before, after = self.bounds_for(READY_CHECKS), self.bounds_for(extended)
        self.assertEqual([j for j, _ in before], list(merge.ready_job_groups(READY_CHECKS)),
                         "the pre-ready run did not make one ci-job call per job of the ready checks")
        before_bound, after_bound = dict(before)[job], dict(after)[job]
        self.assertIsNotNone(before_bound, f"the ci-job call of job {job} has no bound")
        self.assertIsNotNone(after_bound, f"the ci-job call of job {job} has no bound with one more ready check")
        self.assertEqual(after_bound - before_bound, merge.READY_CI_STEP_SECONDS,
                         f"one more ready check moved the bound of job {job}'s ci-job call by {after_bound - before_bound} s, not by "
                         f"READY_CI_STEP_SECONDS ({merge.READY_CI_STEP_SECONDS} s)")


# A child process for ProcessExit: it runs merge's clash_verdict with READY_CLASH_SECONDS small, and one leaf of cross_measure's
# path read hangs in its pool's worker, for 20 s, after it writes the MARK file. Every other leaf answers at once.
CLASH_BOUND = 1
CLASH_CHILD = """
import sys, time
sys.path.insert(0, %(merge_dir)r)
import merge
merge.READY_CLASH_SECONDS = %(bound)d
HANG, MARK, OTHER = %(hang)r, %(mark)r, "d" * 40
def hold():
    open(MARK, "w").close()
    time.sleep(20)
merge.merge_reason = lambda *a, **k: None
merge.fetch_branch_heads = lambda root: (0, "")
merge.git = lambda root, *a, **k: (0, "")
merge.head_holds = lambda *a, **k: False
def changed_paths(root, base, head):
    if HANG == "changed_paths" and head == OTHER:
        hold()
    return {"a.py"}
def conflicting_files(root, ours, theirs):
    if HANG == "conflicting_files":
        hold()
    return ("clean", [])
merge.changed_paths = changed_paths
merge.conflicting_files = conflicting_files
class Host:
    def open_pulls(self):
        return [{"number": 8, "head": {"sha": OTHER}, "base": {"ref": "main"}, "draft": False, "body": ""}]
print(merge.clash_verdict("/nonexistent", 7, "main", Host(), {"head": "c" * 40, "body": ""}), flush=True)
"""


class ProcessExit(unittest.TestCase):
    """A clash read past READY_CLASH_SECONDS returns unknown, and the merge process exits: no worker of cross_measure's
    ThreadPoolExecutor holds it. Each case hangs one of the two pools' work; the child process must exit within the bound + 5 s."""

    def setUp(self):
        self.root = tempfile.mkdtemp(dir=RUN_FOLDER)

    def exit_after_a_hung_worker(self, hang):
        mark = os.path.join(self.root, "entered")
        code = CLASH_CHILD % {"merge_dir": HERE, "bound": CLASH_BOUND, "hang": hang, "mark": mark}
        proc = subprocess.Popen([sys.executable, "-c", code], cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            out, err = proc.communicate(timeout=CLASH_BOUND + 5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            self.assertTrue(os.path.exists(mark), "the hung worker never ran, so this case proves nothing")
            self.fail(f"merge was still running {CLASH_BOUND + 5} s after its clash read ran past {CLASH_BOUND} s: "
                      "a worker of cross_measure's pool held the process at exit")
        self.assertTrue(os.path.exists(mark), "the hung worker never ran, so this case proves nothing")
        self.assertEqual(proc.returncode, 0, err)
        self.assertIn("'unknown', 'open-PR clash'", out, "the clash read did not end as unknown")

    def test_merge_exits_after_a_clash_read_whose_first_pool_hangs(self):
        self.exit_after_a_hung_worker("changed_paths")

    def test_merge_exits_after_a_clash_read_whose_second_pool_hangs(self):
        self.exit_after_a_hung_worker("conflicting_files")


class DebtLintMissing(unittest.TestCase):
    """The debt-close lint does not load: merge then has no READY_DEBT_SECONDS (None). debt_verdict reads unknown, naming the lint,
    and raises nothing. `import merge` still works without the lint (the control)."""

    def setUp(self):
        self.wt = tempfile.mkdtemp(dir=RUN_FOLDER)

    def test_a_debt_lint_that_does_not_load_reads_unknown_naming_the_lint(self):
        err = io.StringIO()
        missing = ImportError("No module named 'check_debt_retire'")
        with unittest.mock.patch.object(merge, "READY_DEBT_SECONDS", None), \
                unittest.mock.patch.object(merge, "load_debt_retire", side_effect=missing), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            try:
                result = merge.debt_verdict(self.wt, "main", None, INFO)
            except Exception as e:
                self.fail(f"debt_verdict raised {type(e).__name__} when the debt lint did not load, instead of an unknown verdict: {e}")
        self.assertNotIn("Traceback", err.getvalue(), "the missing debt lint printed a traceback")
        verdict, name, detail = result
        self.assertEqual((verdict, name), ("unknown", "debt retire"))
        self.assertIn("check_debt_retire", detail, f"the unknown text does not name the lint: {detail!r}")

    def test_import_merge_still_works_when_the_debt_lint_is_missing(self):  # control
        code = "import sys\nsys.modules['check_debt_retire'] = None\nsys.path.insert(0, %r)\nimport merge\nprint('imported')\n" % HERE
        done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("imported", done.stdout)
        self.assertNotIn("Traceback", done.stderr)


if __name__ == "__main__":
    unittest.main()
