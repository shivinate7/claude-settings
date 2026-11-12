#!/usr/bin/env python3
"""Cases for the cap alarm: a main push run's job that ends cancelled at its timeout-minutes cap is red.

Script under test: .github/scripts/cap-alarm.py. SCRIPT_REL names it, and CAP_ALARM overrides the path.

Interface these cases pin:
  python3 .github/scripts/cap-alarm.py --jobs JOBS.json --workflow WORKFLOW.yml --run-id N
  JOBS.json  the jobs API shape: {"jobs": [{"name", "conclusion", "started_at", "completed_at"}, ...]}.
             Timestamps are ISO 8601 with Z. started_at is null when the job never started.
  WORKFLOW   the workflow file. A job's cap is its job-level `timeout-minutes:` (4 spaces in), comment removed.
  stdout's first line is the verdict: alarm, clear or unknown.
  Exit 0 for clear only. alarm and unknown exit non-zero, so a step that runs the script never reads a cap it
  could not judge as green.
  An alarm line names the job, the cap in minutes and the run id.

Rules: a job alarms when its conclusion is cancelled and it ran at least its cap (elapsed >= cap). Any other
conclusion is clear. A cancelled job that never started is clear. A cancelled job with no cap, or with a name
that is no job of the workflow, is unknown. No jobs is unknown.

Cost per main push run: one python3 process, in the job that calls it. It reads the workflow file and one
jobs JSON. It makes no network call, starts no child process and writes no file. TestCost proves the last three.

Run with:  python3 lint/test_cap_alarm.py -v
"""
import contextlib
import datetime
import hashlib
import io
import json
import os
import re
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per test run (lint/_test_temp.py)
RUN_FOLDER = _test_temp.run_folder()  # its sweep of older run folders is proved in lint/test_find_copies.py
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import tracked_tree  # noqa: E402  rm_tree removes the run folder at teardown
from test_windows_split import all_jobs, eval_if  # noqa: E402  the one home of the job reader and the if evaluator
from workflow_steps import job_block  # noqa: E402  the one home of the job block parser

SCRIPT_REL = ".github/scripts/cap-alarm.py"
SCRIPT = os.environ.get("CAP_ALARM") or os.path.join(HERE, "..", SCRIPT_REL)
CHECKS = os.path.join(HERE, "..", ".github", "workflows", "checks.yml")
RUN_ID = "7711223344"
BASE = datetime.datetime(2026, 11, 9, 10, 0, 0, tzinfo=datetime.timezone.utc)
BLOCKED = ["socket.socket", "socket.create_connection", "socket.getaddrinfo", "subprocess.Popen",
           "os.system", "os.popen", "os.posix_spawn", "os.fork"]


def stamp(minutes):
    return (BASE + datetime.timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")


def job(name, conclusion, minutes, started=0):
    """A jobs API entry that ran `minutes`, starting `started` minutes after BASE."""
    return {"name": name, "status": "completed", "conclusion": conclusion,
            "started_at": stamp(started), "completed_at": stamp(started + minutes)}


def never_started(name, conclusion="cancelled"):
    return {"name": name, "status": "completed", "conclusion": conclusion,
            "started_at": None, "completed_at": stamp(5)}


def jobs_doc(*jobs):
    return {"total_count": len(jobs), "jobs": list(jobs)}


def workflow(caps):
    """A workflow with one job per (key, cap) pair. A cap of None writes the job with no timeout-minutes line."""
    lines = ["name: fixture", "on: push", "jobs:"]
    for key, cap in caps:
        lines += [f"  {key}:", "    runs-on: ubuntu-latest"]
        if cap is not None:
            lines.append(f"    timeout-minutes: {cap}")
        lines += ["    steps:", "      - run: echo ok"]
    return "\n".join(lines) + "\n"


FIXTURE_WF = workflow([("guard", 45), ("build", 20), ("lint", None)])

# A run block holds a timeout-minutes line, and a quoted run line holds one too. Neither is a cap.
SCANNER_WF = """name: fixture
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    timeout-minutes: 20 # the cap
    steps:
      - name: "tool # not a comment"
        run: |
          echo "don't stop here"
          timeout-minutes: 1
  lint:
    runs-on: ubuntu-latest
    steps:
      - run: echo "timeout-minutes: 2 # quoted"
"""


def cli(doc, wf_text, run_id=RUN_ID):
    """Run the script on fixture files in a folder under the run folder. -> (exit code, stdout, stderr)."""
    case = tempfile.mkdtemp(dir=RUN_FOLDER)
    jobs_path = os.path.join(case, "jobs.json")
    wf_path = os.path.join(case, "checks.yml")
    with open(jobs_path, "w", encoding="utf-8") as f:
        json.dump(doc, f)
    with open(wf_path, "w", encoding="utf-8") as f:
        f.write(wf_text)
    r = subprocess.run([sys.executable, SCRIPT, "--jobs", jobs_path, "--workflow", wf_path, "--run-id", run_id],
                       capture_output=True, text=True, timeout=120)
    return r.returncode, r.stdout, r.stderr


def verdict(out):
    """The first stdout line, the verdict. Empty when the script printed nothing."""
    lines = out.strip().splitlines()
    return lines[0].strip() if lines else ""


def assert_alarm(case, rc, out, err, job_name, cap):
    case.assertEqual(verdict(out), "alarm", f"not an alarm: stdout {out!r} stderr {err!r}")
    case.assertNotEqual(rc, 0, "an alarm exited 0, so a CI step would read it green")
    case.assertIn(job_name, out + err, f"the alarm does not name the job {job_name}")
    case.assertIn(str(cap), out + err, f"the alarm does not name the cap {cap}")
    case.assertIn(RUN_ID, out + err, "the alarm does not name the run")


def assert_clear(case, rc, out, err):
    case.assertEqual(verdict(out), "clear", f"not clear: stdout {out!r} stderr {err!r}")
    case.assertEqual(rc, 0, "a clear verdict exited non-zero")


def assert_unknown(case, rc, out, err):
    case.assertEqual(verdict(out), "unknown", f"not unknown: stdout {out!r} stderr {err!r}")
    case.assertNotEqual(rc, 0, "an unknown verdict exited 0, so a CI step would read it green")


class TestVerdicts(unittest.TestCase):
    def test_cancelled_at_exact_cap_alarms(self):
        rc, out, err = cli(jobs_doc(job("guard", "cancelled", 45)), FIXTURE_WF)
        assert_alarm(self, rc, out, err, "guard", 45)

    def test_cancelled_over_cap_alarms(self):
        rc, out, err = cli(jobs_doc(job("guard", "cancelled", 50)), FIXTURE_WF)
        assert_alarm(self, rc, out, err, "guard", 45)

    def test_one_capped_job_among_passed_jobs_alarms(self):
        rc, out, err = cli(jobs_doc(job("build", "success", 10), job("guard", "cancelled", 45)), FIXTURE_WF)
        assert_alarm(self, rc, out, err, "guard", 45)

    def test_cancelled_one_minute_under_cap_is_clear(self):
        rc, out, err = cli(jobs_doc(job("guard", "cancelled", 44)), FIXTURE_WF)
        assert_clear(self, rc, out, err)

    def test_cancelled_well_under_cap_is_clear(self):
        rc, out, err = cli(jobs_doc(job("guard", "cancelled", 2)), FIXTURE_WF)
        assert_clear(self, rc, out, err)

    def test_success_at_cap_is_clear(self):
        rc, out, err = cli(jobs_doc(job("guard", "success", 45)), FIXTURE_WF)
        assert_clear(self, rc, out, err)

    def test_skipped_job_is_clear(self):
        rc, out, err = cli(jobs_doc(job("guard", "skipped", 0)), FIXTURE_WF)
        assert_clear(self, rc, out, err)

    def test_cancelled_before_start_is_clear(self):
        rc, out, err = cli(jobs_doc(never_started("guard")), FIXTURE_WF)
        assert_clear(self, rc, out, err)

    def test_missing_cap_is_unknown_not_clear(self):
        rc, out, err = cli(jobs_doc(job("lint", "cancelled", 30)), FIXTURE_WF)
        assert_unknown(self, rc, out, err)

    def test_job_absent_from_workflow_is_unknown_not_clear(self):
        rc, out, err = cli(jobs_doc(job("renamed", "cancelled", 30)), FIXTURE_WF)
        assert_unknown(self, rc, out, err)

    def test_no_jobs_is_unknown_not_clear(self):
        rc, out, err = cli(jobs_doc(), FIXTURE_WF)
        assert_unknown(self, rc, out, err)


class TestScanner(unittest.TestCase):
    def test_a_run_block_timeout_line_is_not_the_cap(self):
        rc, out, err = cli(jobs_doc(job("build", "cancelled", 15)), SCANNER_WF)
        assert_clear(self, rc, out, err)

    def test_a_trailing_comment_after_the_cap_is_stripped(self):
        rc, out, err = cli(jobs_doc(job("build", "cancelled", 20)), SCANNER_WF)
        assert_alarm(self, rc, out, err, "build", 20)

    def test_a_quoted_timeout_in_a_run_line_is_not_a_cap(self):
        rc, out, err = cli(jobs_doc(job("lint", "cancelled", 5)), SCANNER_WF)
        assert_unknown(self, rc, out, err)


class TestRealWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(CHECKS, encoding="utf-8") as f:
            cls.text = f.read()

    def cap_of(self, name):
        block = job_block(self.text, name)
        self.assertIsNotNone(block, f"checks.yml has no job {name}")
        m = re.search(r"^    timeout-minutes:\s*(\d+)", block, re.M)
        self.assertIsNotNone(m, f"{name} has no job-level timeout-minutes number")
        return int(m.group(1))

    def test_the_job_cap_is_read_past_a_step_cap(self):
        # checks-mutate-guard caps the job at 75 and one of its steps at 5. Cancelled at 30 minutes, it is clear.
        cap = self.cap_of("checks-mutate-guard")
        self.assertGreater(cap, 30, "the job cap must sit above the 30 minutes elapsed, or this case proves nothing")
        rc, out, err = cli(jobs_doc(job("checks-mutate-guard", "cancelled", 30)), self.text)
        assert_clear(self, rc, out, err)

    def test_a_comment_after_the_real_cap_is_stripped(self):
        # checks-guard reads `timeout-minutes: 60 # provisional`. Cancelled at its cap, it alarms with that cap.
        cap = self.cap_of("checks-guard")
        rc, out, err = cli(jobs_doc(job("checks-guard", "cancelled", cap)), self.text)
        assert_alarm(self, rc, out, err, "checks-guard", cap)


def snapshot(root):
    """Every file and folder under root, with each file's size and sha256."""
    seen = {}
    for dirpath, dirnames, names in os.walk(root):
        for d in dirnames:
            seen[os.path.relpath(os.path.join(dirpath, d), root) + os.sep] = None
        for n in names:
            p = os.path.join(dirpath, n)
            with open(p, "rb") as f:
                data = f.read()
            seen[os.path.relpath(p, root)] = (len(data), hashlib.sha256(data).hexdigest())
    return seen


class TestCost(unittest.TestCase):
    def in_process(self, doc):
        """Run the script in this process with network, child-process and fork calls all raising.
        -> (stdout, mock calls by name, run folder before, run folder after)."""
        case = tempfile.mkdtemp(dir=RUN_FOLDER)
        jobs_path = os.path.join(case, "jobs.json")
        wf_path = os.path.join(case, "checks.yml")
        with open(jobs_path, "w", encoding="utf-8") as f:
            json.dump(doc, f)
        with open(wf_path, "w", encoding="utf-8") as f:
            f.write(FIXTURE_WF)
        before = snapshot(RUN_FOLDER)
        blocked = {name: mock.Mock(side_effect=AssertionError(f"the script called {name}")) for name in BLOCKED}
        out = io.StringIO()
        with contextlib.ExitStack() as stack:
            for name, m in blocked.items():
                stack.enter_context(mock.patch(name, m, create=True))  # create: os.fork and os.posix_spawn are absent on Windows
            stack.enter_context(mock.patch.object(sys, "argv", [
                SCRIPT, "--jobs", jobs_path, "--workflow", wf_path, "--run-id", RUN_ID]))
            stack.enter_context(contextlib.redirect_stdout(out))
            stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
            try:
                runpy.run_path(SCRIPT, run_name="__main__")
            except SystemExit:
                pass
        after = snapshot(RUN_FOLDER)
        return out.getvalue(), {name: m.call_count for name, m in blocked.items()}, before, after

    def assert_no_side_effects(self, calls, before, after):
        for name, count in calls.items():
            self.assertEqual(count, 0, f"the script reached {name}")
        self.assertEqual(after, before, "the script wrote to the run folder")

    def test_an_alarm_comes_out_with_no_network_no_child_process_and_no_file_written(self):
        out, calls, before, after = self.in_process(jobs_doc(job("guard", "cancelled", 45)))
        self.assertEqual(verdict(out), "alarm", f"the verdict did not come out with the calls blocked: {out!r}")
        self.assert_no_side_effects(calls, before, after)

    def test_a_clear_comes_out_with_no_network_no_child_process_and_no_file_written(self):
        out, calls, before, after = self.in_process(jobs_doc(job("guard", "cancelled", 2)))
        self.assertEqual(verdict(out), "clear", f"the verdict did not come out with the calls blocked: {out!r}")
        self.assert_no_side_effects(calls, before, after)


def runs_on_push(cond):
    """True when a job runs on a push: no if, or an if that reads true for push. An if this reader cannot evaluate
    counts as push, as lint/all_jobs_passed_rules.py counts it."""
    if cond is None:
        return True
    try:
        return eval_if(cond, "push", "true")
    except Exception:
        return True


class TestWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(CHECKS, encoding="utf-8") as f:
            cls.text = f.read()
        cls.jobs = all_jobs(cls.text)
        cls.push_jobs = [n for n, j in cls.jobs.items() if runs_on_push(j["if"])]
        cls.runners = [n for n in cls.push_jobs if SCRIPT_REL in (job_block(cls.text, n) or "")]

    def test_some_job_on_a_main_push_runs_the_cap_alarm(self):
        self.assertTrue(self.push_jobs, "the reader found no job of checks.yml that runs on a push")
        self.assertTrue(self.runners, f"no job that runs on a main push runs {SCRIPT_REL}")

    def test_the_job_that_runs_the_cap_alarm_runs_after_a_cancelled_need(self):
        self.assertTrue(self.push_jobs, "the reader found no job of checks.yml that runs on a push")
        self.assertTrue(self.runners, f"no job that runs on a main push runs {SCRIPT_REL}")
        for name in self.runners:
            cond = self.jobs[name]["if"] or ""
            self.assertTrue("always()" in cond or "!cancelled()" in cond,
                            f"{name} runs the cap alarm with no always() or !cancelled(), so GitHub skips it "
                            f"when a needed job is cancelled: {cond!r}")


def tearDownModule():
    tracked_tree.rm_tree(RUN_FOLDER)  # test-temp-standard: teardown removes the run folder


if __name__ == "__main__":
    unittest.main()
