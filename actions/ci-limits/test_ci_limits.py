#!/usr/bin/env python3
"""Cases for actions/ci-limits/ci_limits.py: each CI job's time limit, read from green runs (decision ci-job-caps,
restart-plan R3). Stdlib only.

    python3 actions/ci-limits/test_ci_limits.py

These cases pin the interface of ci_limits.py:

  job_limits(jobs_by_run, caps, kinds=None, window=30, cut_counts_as_sample=True) -> (limits, misjudged)
      jobs_by_run: completed push runs on main, newest first: [{"run_id": int, "jobs": [jobs-API job, ...]}].
      caps: {job name: timeout-minutes in force}. A job cancelled at or past its cap is a cut sample.
      cut_counts_as_sample=False ignores a cut run: a limit is then the green max x 1.5, floored by the median.
      kinds: {job name: kind}. limits: {job name: minutes, "job/step": minutes}, over every name in caps.
      misjudged: the job names cut at their estimate while still new.
  deadline_minutes(jobs_by_run, limits, window=30) -> minutes. limits holds the job-level limits only.
  read_limits(fetch, caps, kinds=None, window=30) -> (limits, misjudged, warnings). fetch() returns jobs_by_run,
      or raises. limits adds "deadlineMinutes". An error gives every limit 360 and one warning line.
  main(argv, fetch, caps, kinds=None, out=None, err=None) -> exit code. argv is ["--json"] or ["--table"],
      and "--green-only" may follow it: that sets cut_counts_as_sample=False.
      Warnings go to err; the JSON or the table goes to out.

Minutes are whole seconds over 60, read from the fixtures' own timestamps. No clock is injected, and nothing sleeps.
The module under test loads from CI_LIMITS_UNDER_TEST when set (the red-run stand-in, ci_limits_stub_test.py),
else from ci_limits.py beside this file.
"""
import builtins
import datetime
import importlib.util
import inspect
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lint"))
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)

UNDER_TEST = os.environ.get("CI_LIMITS_UNDER_TEST") or os.path.join(HERE, "ci_limits.py")
_spec = importlib.util.spec_from_file_location("ci_limits_under_test", UNDER_TEST)
ci_limits = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ci_limits)

T0 = datetime.datetime(2026, 11, 10, 10, 0, 0, tzinfo=datetime.timezone.utc)


def ts(minutes):
    """A jobs-API timestamp `minutes` after T0, in whole seconds."""
    at = T0 + datetime.timedelta(seconds=round(minutes * 60))
    return at.strftime("%Y-%m-%dT%H:%M:%SZ")


def step(name, start, minutes, conclusion="success"):
    return {"name": name, "status": "completed", "conclusion": conclusion,
            "started_at": ts(start), "completed_at": ts(start + minutes)}


def job(name, minutes, conclusion="success", start=0.0, steps=()):
    return {"name": name, "status": "completed", "conclusion": conclusion,
            "started_at": ts(start), "completed_at": ts(start + minutes), "steps": list(steps)}


def run(run_id, *jobs):
    return {"run_id": run_id, "jobs": list(jobs)}


def single_job_limit(minutes):
    """The limit of one job, `checks`, whose only sample is a green run of `minutes`."""
    limits, _ = ci_limits.job_limits([run(1, job("checks", minutes))], {"checks": 999})
    return limits.get("checks")


# Six jobs. lint-a, lint-c and lint-d are green at 20 min (limit 30 each). They are the peers that keep the median
# floor below the claims: every limit is at least the median of all limits. checks is green at 50 min (limit 75, the
# largest old limit). lint-b is new and of lint-a's kind, so its estimate is 30 x 1.5 = 45. docs is new with no kind
# match, so its estimate is 75 x 1.5 = 112.5, rounded up to 113.
CAPS = {"lint-a": 30, "lint-b": 45, "lint-c": 30, "lint-d": 30, "checks": 75, "docs": 60}
KINDS = {"lint-a": "lint", "lint-b": "lint", "lint-c": "lint", "lint-d": "lint", "checks": "test", "docs": "docs"}
OLD_RUNS = [run(2, job("lint-a", 20), job("checks", 50), job("lint-c", 20), job("lint-d", 20)),
            run(1, job("lint-a", 20), job("checks", 50), job("lint-c", 20), job("lint-d", 20))]


def raising_fetch():
    raise OSError("jobs API: HTTP 503")


class SampleRules(unittest.TestCase):
    def test_failed_attempt_is_not_a_sample(self):
        runs = [run(3, job("checks-guard", 40, "failure", steps=[step("Guard suite", 0, 40, "failure")])),
                run(2, job("checks-guard", 20))]
        limits, _ = ci_limits.job_limits(runs, {"checks-guard": 60})
        self.assertIn("checks-guard", limits, "checks-guard has no limit")
        self.assertEqual(limits["checks-guard"], 30,
                         "a real test failure (40 min) set the limit: only the green 20 min run counts")

    def test_cut_at_its_cap_is_a_sample(self):
        runs = [run(3, job("checks-guard", 27.25, "cancelled")), run(2, job("checks-guard", 20))]
        limits, misjudged = ci_limits.job_limits(runs, {"checks-guard": 27})
        self.assertIn("checks-guard", limits, "checks-guard has no limit")
        self.assertEqual(limits["checks-guard"], 41,
                         "a job cut at its 27 min cap (27.25 min) must set the limit: 27.25 x 1.5 rounds up to 41")
        self.assertEqual(sorted(misjudged), [], "an old job cut at its cap was flagged misjudged")

    def test_cut_before_its_cap_is_not_a_sample(self):
        # Cancelled at 12 min by a newer push, well short of its 27 min cap.
        runs = [run(3, job("checks-guard", 12, "cancelled")), run(2, job("checks-guard", 10))]
        limits, _ = ci_limits.job_limits(runs, {"checks-guard": 27})
        self.assertIn("checks-guard", limits, "checks-guard has no limit")
        self.assertEqual(limits["checks-guard"], 15,
                         "a cancel at 12 min, short of the 27 min cap, counted as a sample: 12 x 1.5 = 18, want 15")

    def test_margin_multiplies_the_slowest_sample(self):
        self.assertEqual(single_job_limit(20), 30, "20 min x 1.5 is 30; a +5 margin would give 25")
        self.assertEqual(single_job_limit(21), 32, "21 min x 1.5 is 31.5, which rounds up to 32")
        self.assertEqual(single_job_limit(50), 75, "50 min x 1.5 is 75; a +5 margin would give 55")

    def test_limit_is_clamped_to_360(self):
        self.assertEqual(single_job_limit(200), 300, "200 min x 1.5 is 300, under the clamp")
        self.assertEqual(single_job_limit(300), 360, "300 min x 1.5 is 450: the limit must clamp to 360")

    def test_window_is_the_newest_30_runs(self):
        runs = [run(i, job("checks", 10)) for i in range(30, 0, -1)] + [run(0, job("checks", 100))]
        limits, _ = ci_limits.job_limits(runs, {"checks": 75})
        self.assertIn("checks", limits, "checks has no limit")
        self.assertEqual(limits["checks"], 15,
                         "the oldest run (100 min) is the 31st, outside the newest 30, and must not count")

    def test_empty_window_gives_no_limits(self):
        self.assertEqual(ci_limits.job_limits([], {}), ({}, []),
                         "an empty window must give no limits and no misjudged jobs")


class NewJobs(unittest.TestCase):
    def test_new_job_takes_its_kind_times_1_5(self):
        limits, misjudged = ci_limits.job_limits(OLD_RUNS, CAPS, KINDS)
        self.assertIn("lint-b", limits, "lint-b (new, in no run) has no limit")
        self.assertEqual(limits["lint-b"], 45,
                         "lint-b is new and lint-a is its kind at 30: 30 x 1.5 = 45, not the largest 75 x 1.5")
        self.assertEqual(sorted(misjudged), [], "a new job with no cut was flagged misjudged")

    def test_new_job_without_a_kind_match_takes_largest_times_1_5(self):
        limits, _ = ci_limits.job_limits(OLD_RUNS, CAPS, KINDS)
        self.assertIn("docs", limits, "docs has no limit")
        self.assertEqual(limits["docs"], 113,
                         "docs has no job of its kind: the largest old job is checks at 75, and 75 x 1.5 = 112.5 is 113")

    def test_new_job_estimate_clamps_to_360(self):
        runs = [run(1, job("lint-a", 20), job("checks", 200))]
        limits, _ = ci_limits.job_limits(runs, CAPS, KINDS)
        self.assertIn("docs", limits, "docs has no limit")
        self.assertEqual(limits["docs"], 360,
                         "docs takes checks' limit 300 x 1.5 = 450, which must clamp to 360")

    def test_first_green_run_ends_new(self):
        runs = [run(3, job("lint-b", 40))] + OLD_RUNS
        limits, misjudged = ci_limits.job_limits(runs, CAPS, KINDS)
        self.assertIn("lint-b", limits, "lint-b has no limit")
        self.assertEqual(limits["lint-b"], 60,
                         "lint-b had its first green run (40 min): its limit is 40 x 1.5 = 60, not its estimate 45")
        self.assertEqual(sorted(misjudged), [], "lint-b, now with a green run, was flagged misjudged")

    def test_new_job_cut_at_its_estimate_is_misjudged_and_takes_largest(self):
        runs = [run(3, job("lint-b", 45.5, "cancelled"))] + OLD_RUNS
        limits, misjudged = ci_limits.job_limits(runs, CAPS, KINDS)
        self.assertIn("lint-b", limits, "lint-b has no limit")
        self.assertEqual(limits["lint-b"], 113,
                         "lint-b, new and cut at its estimate 45, must take the largest 75 x 1.5 = 113")
        self.assertEqual(sorted(misjudged), ["lint-b"], "lint-b was cut at its estimate and not flagged misjudged")

    def test_old_job_cut_is_never_misjudged(self):
        runs = [run(3, job("checks", 76, "cancelled"))] + OLD_RUNS
        limits, misjudged = ci_limits.job_limits(runs, CAPS, KINDS)
        self.assertIn("checks", limits, "checks has no limit")
        self.assertEqual(limits["checks"], 114,
                         "checks, an old job cut at its 75 min cap (76 min), must rise to 76 x 1.5 = 114")
        self.assertEqual(sorted(misjudged), [], "an old job cut at its cap was flagged misjudged")


class StepLimits(unittest.TestCase):
    def test_step_limit_is_keyed_job_slash_step(self):
        runs = [run(1, job("checks-guard", 23, steps=[step("Install", 0, 2),
                                                      step("Guard fixture suite (shard 2 of 2)", 2, 21)]))]
        limits, _ = ci_limits.job_limits(runs, {"checks-guard": 60})
        self.assertIn("checks-guard/Install", limits, "no step limit under the key checks-guard/Install")
        self.assertEqual(limits["checks-guard/Install"], 3, "Install took 2 min: 2 x 1.5 = 3")
        key = "checks-guard/Guard fixture suite (shard 2 of 2)"
        self.assertIn(key, limits, "no step limit under the key " + key)
        self.assertEqual(limits[key], 32, "the Guard suite step took 21 min: 21 x 1.5 = 31.5 rounds up to 32")

    def test_failed_step_is_not_a_sample(self):
        name = "Guard fixture suite (shard 2 of 2)"
        runs = [run(2, job("checks-guard", 40, "failure", steps=[step(name, 0, 40, "failure")])),
                run(1, job("checks-guard", 20, steps=[step(name, 0, 20)]))]
        limits, _ = ci_limits.job_limits(runs, {"checks-guard": 60})
        key = "checks-guard/" + name
        self.assertIn(key, limits, "no step limit under the key " + key)
        self.assertEqual(limits[key], 30,
                         "a real failure in a 40 min step set the step limit: only the green 20 min step counts")


class Deadline(unittest.TestCase):
    def test_deadline_is_1_5x_the_wall_clock_not_plus_5(self):
        # The jobs start at 0 and 20 and end at 10 and 50, so the run takes 50 min wall clock.
        runs = [run(1, job("checks", 10, start=0), job("checks-guard", 30, start=20))]
        got = ci_limits.deadline_minutes(runs, {"checks": 15, "checks-guard": 45})
        self.assertEqual(got, 75,
                         "wall clock 50 min x 1.5 is 75; +5 gives 55, and a sum of job minutes gives 60")

    def test_deadline_is_floored_at_the_largest_job_limit_not_plus_5(self):
        runs = [run(1, job("checks", 10))]
        got = ci_limits.deadline_minutes(runs, {"checks": 99, "docs": 149})
        self.assertEqual(got, 149,
                         "the largest job limit is 149 and 10 min x 1.5 is 15: the floor is 149, not +5 (154)")

    def test_deadline_is_clamped_to_360(self):
        runs = [run(1, job("checks", 300))]
        got = ci_limits.deadline_minutes(runs, {"checks": 100})
        self.assertEqual(got, 360, "300 min x 1.5 is 450: the deadline must clamp to 360")


class ApiError(unittest.TestCase):
    def test_api_error_gives_every_limit_360_and_one_warning(self):
        limits, misjudged, warnings = ci_limits.read_limits(raising_fetch, {"lint-a": 30, "checks": 75})
        for key in ("lint-a", "checks", "deadlineMinutes"):
            self.assertEqual(limits.get(key), 360, key + " is not 360 after an API error")
        self.assertEqual(len(warnings), 1, "an API error must print one warning line, got %r" % (warnings,))
        self.assertIn("360", warnings[0], "the warning does not say the limits are 360")


class Cli(unittest.TestCase):
    def cli(self, argv, fetch):
        out, err = io.StringIO(), io.StringIO()
        rc = ci_limits.main(argv, fetch=fetch, caps=CAPS, kinds=KINDS, out=out, err=err)
        return rc, out.getvalue(), err.getvalue()

    def test_json_prints_key_minutes(self):
        rc, out, err = self.cli(["--json"], lambda: OLD_RUNS)
        self.assertEqual(rc, 0, "--json exited %r, want 0" % (rc,))
        self.assertTrue(out.lstrip().startswith("{"), "--json printed no JSON object: %r" % (out[:80],))
        self.assertEqual(err, "", "--json wrote to stderr with no API error: %r" % (err,))
        got = json.loads(out)
        self.assertEqual(got.get("checks"), 75, "checks: want 75 from its green 50 min runs")
        self.assertEqual(got.get("lint-b"), 45, "lint-b (new) should be 45 from lint-a's kind")
        self.assertEqual(got.get("deadlineMinutes"), 113,
                         "the deadline is floored at the largest job limit, docs (new) at 113")

    def test_table_is_markdown_and_flags_misjudged(self):
        runs = [run(3, job("lint-b", 45.5, "cancelled"))] + OLD_RUNS
        rc, out, _ = self.cli(["--table"], lambda: runs)
        self.assertEqual(rc, 0, "--table exited %r, want 0" % (rc,))
        lines = [line for line in out.splitlines() if line.strip()]
        self.assertTrue(lines, "--table printed nothing")
        self.assertTrue(all(line.startswith("|") for line in lines),
                        "--table printed a line that is not a markdown table row: %r" % (lines,))
        self.assertTrue(any(re.search(r"\|\s*checks\s*\|\s*75\s*\|", line) for line in lines),
                        "no table row reads checks at 75")
        lint_b = [line for line in lines if "lint-b" in line]
        self.assertTrue(lint_b, "no table row for lint-b")
        self.assertIn("misjudged", lint_b[0], "the lint-b row does not flag misjudged")

    def test_api_error_warning_goes_to_stderr_and_limits_to_stdout(self):
        rc, out, err = self.cli(["--json"], raising_fetch)
        self.assertEqual(rc, 0, "an API error must not fail the command")
        self.assertEqual(len(err.splitlines()), 1, "an API error must print one warning line on stderr: %r" % (err,))
        self.assertTrue(out.lstrip().startswith("{"), "--json printed no JSON object after an API error")
        got = json.loads(out)
        for key in ("lint-a", "lint-b", "checks", "docs", "deadlineMinutes"):
            self.assertEqual(got.get(key), 360, key + " is not 360 after an API error")


RUN_FOLDER = None


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()  # test-temp-standard: this run's folder, old siblings swept


def tearDownModule():
    if RUN_FOLDER and os.path.isdir(RUN_FOLDER):
        shutil.rmtree(RUN_FOLDER, ignore_errors=True)


class MedianFloor(unittest.TestCase):
    def test_green_40_second_job_takes_the_median_not_one_minute(self):
        caps = {"tiny": 5, "lint-a": 30, "checks": 75}
        runs = [run(1, job("tiny", 40 / 60), job("lint-a", 20), job("checks", 50))]
        limits, _ = ci_limits.job_limits(runs, caps)
        self.assertEqual(limits["tiny"], 30,
                         "tiny ran 40 s and got %r minute(s): every limit is at least the median of all limits, 30"
                         % (limits["tiny"],))

    def test_job_cut_at_61_seconds_on_a_1_minute_cap_cannot_get_1(self):
        caps = {"cut-job": 1, "lint-a": 30, "checks": 75}
        runs = [run(2, job("cut-job", 61 / 60, "cancelled")),
                run(1, job("cut-job", 40 / 60), job("lint-a", 20), job("checks", 50))]
        limits, _ = ci_limits.job_limits(runs, caps)
        self.assertGreaterEqual(limits["cut-job"], 2,
                                "cut-job was cut at 61 s on a 1 min cap and got %r: the cut is a sample of 61 s, "
                                "so its limit is at least 2" % (limits["cut-job"],))


class CutRule(unittest.TestCase):
    def test_cut_at_62_minutes_on_a_60_minute_cap_is_a_sample(self):
        runs = [run(2, job("checks-guard", 62, "cancelled")), run(1, job("checks-guard", 20))]
        limits, _ = ci_limits.job_limits(runs, {"checks-guard": 60})
        self.assertEqual(limits["checks-guard"], 93,
                         "a 62 min cut on a 60 min cap is a sample: 62 x 1.5 = 93, got %r" % (limits["checks-guard"],))

    def test_cancelled_at_5_minutes_on_a_60_minute_cap_is_not_a_sample(self):
        runs = [run(2, job("checks-guard", 5, "cancelled")), run(1, job("checks-guard", 20))]
        limits, _ = ci_limits.job_limits(runs, {"checks-guard": 60})
        self.assertEqual(limits["checks-guard"], 30,
                         "a cancel at 5 min, short of the 60 min cap, is no sample: 20 x 1.5 = 30, got %r"
                         % (limits["checks-guard"],))

    def test_new_job_cancelled_at_5_minutes_is_not_misjudged(self):
        runs = [run(3, job("lint-b", 5, "cancelled"))] + OLD_RUNS
        limits, misjudged = ci_limits.job_limits(runs, CAPS, KINDS)
        self.assertEqual(misjudged, [], "a new job cancelled at 5 min, short of its cap, was flagged misjudged")
        self.assertEqual(limits["lint-b"], 45, "lint-b cancelled at 5 min is new: its estimate 45 stands, got %r"
                         % (limits["lint-b"],))


SKIPPED_CAPS = {"all-jobs-passed": 60, "lint-a": 30, "checks": 75}


def skipped_runs():
    """all-jobs-passed is skipped in every run of the window: a skipped job has zero minutes on the jobs API."""
    return [run(2, job("all-jobs-passed", 0, "skipped"), job("lint-a", 20), job("checks", 50)),
            run(1, job("all-jobs-passed", 0, "skipped"), job("lint-a", 20), job("checks", 50))]


def runs_without_skipped_job():
    return [run(2, job("lint-a", 20), job("checks", 50)), run(1, job("lint-a", 20), job("checks", 50))]


class NotMeasured(unittest.TestCase):
    def test_job_skipped_in_every_run_has_no_limit(self):
        runs = skipped_runs()
        self.assertTrue(all(j["conclusion"] == "skipped" for r in runs for j in r["jobs"]
                            if j["name"] == "all-jobs-passed"), "fixture: all-jobs-passed is not skipped in every run")
        limits, _ = ci_limits.job_limits(runs, SKIPPED_CAPS)
        self.assertIn("all-jobs-passed", limits, "all-jobs-passed has no key at all")
        self.assertIsNone(limits["all-jobs-passed"],
                          "all-jobs-passed was skipped in every run and got %r: it never ran on main, so no limit"
                          % (limits["all-jobs-passed"],))

    def test_table_says_not_measured_on_main(self):
        out, err = io.StringIO(), io.StringIO()
        rc = ci_limits.main(["--table"], fetch=lambda: skipped_runs(), caps=SKIPPED_CAPS, out=out, err=err)
        self.assertEqual(rc, 0, "--table exited %r, want 0" % (rc,))
        rows = [line for line in out.getvalue().splitlines() if line.startswith("| all-jobs-passed |")]
        self.assertEqual(len(rows), 1, "no table row for all-jobs-passed: %r" % (out.getvalue(),))
        self.assertIn("| not measured on main |", rows[0],
                      "the all-jobs-passed row does not say 'not measured on main': %r" % (rows[0],))

    def test_json_prints_null_for_a_job_skipped_in_every_run(self):
        out, err = io.StringIO(), io.StringIO()
        rc = ci_limits.main(["--json"], fetch=lambda: skipped_runs(), caps=SKIPPED_CAPS, out=out, err=err)
        self.assertEqual(rc, 0, "--json exited %r, want 0" % (rc,))
        got = json.loads(out.getvalue())
        self.assertIn("all-jobs-passed", got, "the JSON has no all-jobs-passed key")
        self.assertIsNone(got["all-jobs-passed"],
                          "the JSON gives all-jobs-passed %r, want null" % (got["all-jobs-passed"],))

    def test_skipped_job_joins_no_median(self):
        with_, _ = ci_limits.job_limits(skipped_runs(), SKIPPED_CAPS)
        without, _ = ci_limits.job_limits(runs_without_skipped_job(), {"lint-a": 30, "checks": 75})
        for name in ("lint-a", "checks"):
            self.assertEqual(with_[name], without[name],
                             "%s is %r with the skipped job in the window and %r without: a job skipped in every run "
                             "must join no median" % (name, with_[name], without[name]))

    def test_skipped_job_adds_nothing_to_the_deadline(self):
        with_, _, _ = ci_limits.read_limits(skipped_runs, SKIPPED_CAPS)
        without, _, _ = ci_limits.read_limits(runs_without_skipped_job, {"lint-a": 30, "checks": 75})
        self.assertEqual(with_["deadlineMinutes"], without["deadlineMinutes"],
                         "the deadline is %r with the skipped job and %r without: a job skipped in every run must "
                         "not raise it" % (with_["deadlineMinutes"], without["deadlineMinutes"]))

    def test_job_skipped_in_only_some_runs_keeps_a_limit(self):
        runs = [run(2, job("all-jobs-passed", 0, "skipped"), job("lint-a", 20)),
                run(1, job("all-jobs-passed", 10), job("lint-a", 20))]
        limits, _ = ci_limits.job_limits(runs, SKIPPED_CAPS)
        self.assertIsNotNone(limits["all-jobs-passed"],
                             "all-jobs-passed ran green in one run of the window and lost its limit")


def job_rows(count):
    return [job("checks-%d" % i, 1) for i in range(count)]


def fake_jobs_api(rows_by_run, calls):
    """A gh_api stand-in: the run list (newest first), then each run's job rows, paged as the jobs API pages
    (`page`, `per_page`, `total_count`). A call without `page` reads page 1."""
    def api(path, *fields):
        calls.append(path)
        if path.endswith("/runs"):
            return {"workflow_runs": [{"id": rid} for rid in rows_by_run]}
        run_id = int(path.split("/actions/runs/")[1].split("/")[0])
        kv = dict(f.split("=", 1) for f in fields)
        per_page, page = int(kv.get("per_page", 30)), int(kv.get("page", 1))
        rows = rows_by_run[run_id]
        start = (page - 1) * per_page
        return {"total_count": len(rows), "jobs": rows[start:start + per_page]}
    return api


def fetch_with(rows_by_run, calls):
    with mock.patch.object(ci_limits, "gh_api", fake_jobs_api(rows_by_run, calls)):
        return ci_limits.fetch_runs()


class FetchRuns(unittest.TestCase):
    def test_fetch_runs_reads_all_130_job_rows_of_a_run(self):
        rows = job_rows(130)
        runs = fetch_with({1: rows, 2: job_rows(5)}, [])
        self.assertEqual([r["run_id"] for r in runs], [1, 2], "fixture: the runs are not listed newest first")
        self.assertEqual(len(runs[0]["jobs"]), 130,
                         "run 1 has 130 job rows and fetch_runs kept %d: the jobs are read one page only"
                         % len(runs[0]["jobs"]))
        self.assertEqual([j["name"] for j in runs[0]["jobs"]], [j["name"] for j in rows],
                         "the 130 job rows came back out of order or changed")

    def test_fetch_runs_makes_one_list_call_plus_one_per_run_plus_extra_pages(self):
        calls = []
        fetch_with({1: job_rows(130), 2: job_rows(5)}, calls)
        self.assertEqual(len(calls), 4,
                         "1 list call + 2 run calls + 1 extra page of run 1 = 4 calls, got %d" % len(calls))

    def test_fetch_runs_starts_no_process_of_its_own(self):
        spawned = []

        def refuse(*args, **kwargs):
            spawned.append(args)
            raise OSError("fetch_runs started a process of its own")

        with mock.patch.object(subprocess, "Popen", side_effect=refuse), \
                mock.patch.object(subprocess, "run", side_effect=refuse):
            fetch_with({1: job_rows(130), 2: job_rows(5)}, [])
        self.assertEqual(spawned, [], "fetch_runs started %d process(es) of its own" % len(spawned))

    def test_fetch_runs_writes_nothing(self):
        writes = []
        real_open = builtins.open

        def recording_open(file, mode="r", *args, **kwargs):
            if any(c in mode for c in "wax+"):
                writes.append((str(file), mode))
            return real_open(file, mode, *args, **kwargs)

        with mock.patch.object(builtins, "open", recording_open):
            fetch_with({1: job_rows(130), 2: job_rows(5)}, [])
        self.assertEqual(writes, [], "fetch_runs opened a file for writing: %r" % (writes,))

    def test_run_with_no_jobs_reads_one_page(self):
        calls = []
        runs = fetch_with({1: []}, calls)
        self.assertEqual(runs[0]["jobs"], [], "an empty run came back with jobs")
        self.assertEqual(len(calls), 2, "1 list call + 1 page for an empty run = 2 calls, got %d" % len(calls))

    def test_run_of_exactly_100_rows_reads_one_page(self):
        calls = []
        runs = fetch_with({1: job_rows(100)}, calls)
        self.assertEqual(len(runs[0]["jobs"]), 100, "a run of 100 rows came back with %d" % len(runs[0]["jobs"]))
        self.assertEqual(len(calls), 2, "1 list call + 1 page for 100 rows = 2 calls, got %d" % len(calls))


CHECKS_YML = ("name: checks\non: push\njobs:\n  checks:\n    runs-on: ubuntu-latest\n"
              "    timeout-minutes: %d\n    steps:\n      - run: echo ok\n")


def git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=ci-limits-test", "-c", "user.email=ci-limits-test@example.invalid", *args],
                   cwd=cwd, check=True, capture_output=True, text=True)


class WorkflowCapsRef(unittest.TestCase):
    """main has 60, HEAD (branch work) has 20, the checkout has 5 uncommitted: each reading is a different number."""

    def setUp(self):
        self.root = tempfile.mkdtemp(dir=RUN_FOLDER)
        self.checks_yml(60)
        git(self.root, "init", "-q")
        git(self.root, "checkout", "-q", "-b", "main")
        git(self.root, "add", ".github")
        git(self.root, "commit", "-q", "-m", "main: timeout 60")
        git(self.root, "checkout", "-q", "-b", "work")
        self.checks_yml(20)
        git(self.root, "commit", "-q", "-am", "work: timeout 20")
        self.checks_yml(5)

    def checks_yml(self, minutes):
        folder = os.path.join(self.root, ".github", "workflows")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "checks.yml"), "w", encoding="utf-8") as f:
            f.write(CHECKS_YML % minutes)

    def test_workflow_caps_reads_the_named_ref_not_the_checkout(self):
        params = inspect.signature(ci_limits.workflow_caps).parameters
        self.assertIn("ref", params, "workflow_caps takes no ref: it reads the checkout's checks.yml, not a named ref")
        self.assertIn("root", params, "workflow_caps takes no root: it cannot read another repo's ref")
        caps = ci_limits.workflow_caps("main", self.root)
        self.assertEqual(caps.get("checks"), 60,
                         "checks on main is 60 (the checkout says 5, HEAD says 20), got %r" % (caps.get("checks"),))


# checks-guard: green at 20 min (limit 30), and cut at 62 on its 60 min cap, so counting the cut gives 62 x 1.5 = 93.
# Ignoring the cut gives the green 30, floored by the median of 30 and checks' 60, which is 45.
SWITCH_CAPS = {"checks-guard": 60, "checks": 75}
SWITCH_RUNS = [run(2, job("checks-guard", 62, "cancelled"), job("checks", 40)),
               run(1, job("checks-guard", 20), job("checks", 40))]


class CutSwitch(unittest.TestCase):
    def test_default_counts_a_62_minute_cut_on_a_60_minute_cap(self):
        limits, _ = ci_limits.job_limits(SWITCH_RUNS, SWITCH_CAPS)
        self.assertEqual(limits["checks-guard"], 93,
                         "by default a 62 min cut is a sample: 62 x 1.5 = 93, got %r" % (limits["checks-guard"],))

    def test_switch_off_ignores_the_cut_and_floors_the_green_limit_at_the_median(self):
        params = inspect.signature(ci_limits.job_limits).parameters
        self.assertIn("cut_counts_as_sample", params,
                      "job_limits has no cut_counts_as_sample switch: a cut run always counts as a sample")
        limits, _ = ci_limits.job_limits(SWITCH_RUNS, SWITCH_CAPS, cut_counts_as_sample=False)
        self.assertEqual(limits["checks-guard"], 45,
                         "with the cut ignored checks-guard is its green 30, floored by the median 45, got %r"
                         % (limits["checks-guard"],))

    def test_cli_default_counts_the_cut(self):
        out, err = io.StringIO(), io.StringIO()
        rc = ci_limits.main(["--json"], fetch=lambda: SWITCH_RUNS, caps=SWITCH_CAPS, out=out, err=err)
        self.assertEqual(rc, 0, "--json exited %r, want 0" % (rc,))
        self.assertEqual(json.loads(out.getvalue())["checks-guard"], 93,
                         "--json without --green-only should count the 62 min cut: 93")

    def test_cli_green_only_flag_ignores_the_cut(self):
        out, err = io.StringIO(), io.StringIO()
        try:
            rc = ci_limits.main(["--json", "--green-only"], fetch=lambda: SWITCH_RUNS, caps=SWITCH_CAPS,
                                out=out, err=err)
        except SystemExit:
            self.fail("main rejects --green-only: the CLI has no switch, so a cut always counts as a sample")
        self.assertEqual(rc, 0, "--json --green-only exited %r, want 0" % (rc,))
        self.assertEqual(json.loads(out.getvalue())["checks-guard"], 45,
                         "--green-only should ignore the cut: checks-guard is 45")


if __name__ == "__main__":
    unittest.main()
