#!/usr/bin/env python3
"""Tests for .github/scripts/nightly-skip.py, the step that lets the daily scheduled run skip.

The gate writes skip=true to $GITHUB_OUTPUT only when every one of these holds (owner page item 880, 11:53 CST Nov 15):
  (a) the newest schedule run of checks.yml, other than this run, is completed and succeeded, and no other schedule
      run is still going;
  (b) every push run of checks.yml on main created after that green daily concluded success AND was proven by the
      push skip (its push-skip job succeeded and its scope job was skipped), and no push run after it is still going;
  (c) the newest push run of checks.yml on main has this run's head sha;
  (d) the push runs read reach the green daily: a full page of push runs (100) must not end newer than it.
Any read failure writes skip=false and says "unknown". Each push run record carries its jobs (the jobs read), so a push
run with no jobs read is unproven.

The gate also prints the range line, `range: <green daily head>..<this head> (<N> merges)`, to stdout and to
$GITHUB_STEP_SUMMARY, where N counts the push runs created after the green daily; `range: unknown (no green daily)`
when there is none.

RUNS_JSON is the stand-in for the runs read: a JSON list of run records in the shape of the Actions runs API, with a
`jobs` list in the shape of the jobs API on each push run. GITHUB_RUN_ID is this run; its own record does not block.
The test never reaches the network.

    python3 lint/test_nightly_skip.py
"""
import contextlib
import http.client
import importlib.util
import io
import itertools
import json
import os
import shutil
import subprocess
import sys
import unittest
import urllib.error
import urllib.parse
import uuid
from unittest import mock

import _test_temp  # noqa: E402  test-temp-standard: every temp path comes from this run's folder

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP = os.path.join(ROOT, ".github", "scripts", "nightly-skip.py")
RUN_FOLDER = _test_temp.run_folder()  # one run folder per test run; teardown removes it

WORKFLOW = ".github/workflows/checks.yml"
HEAD = "1" * 40  # main's head, the sha the gate is asked about
OTHER = "2" * 40
MERGE = "3" * 40  # a push run's head between the green daily and this head
OLDER = "2026-11-09T03:17:00Z"  # a green daily, the base the cases start from
MID = "2026-11-10T12:00:00Z"  # a push run after OLDER
NEWER = "2026-11-11T03:17:00Z"
LATE = "2026-11-11T12:00:00Z"  # a push run after NEWER
BEFORE = "2026-11-08T12:00:00Z"  # a push run before OLDER
SELF_RUN = 9000  # this run's id, the GITHUB_RUN_ID the gate is given
PAGE = 100  # the runs page size the gate reads
SKIP_MISSING = "nightly-skip.py is missing at .github/scripts/nightly-skip.py, so no gate decides the nightly skip"
STRIPPED = ("RUNS_JSON", "GH_TOKEN", "REPO", "HEAD_SHA", "GITHUB_OUTPUT", "GITHUB_STEP_SUMMARY", "GITHUB_RUN_ID")
_ids = itertools.count(100)


def run(event, sha=HEAD, conclusion="success", created=NEWER, status="completed", path=WORKFLOW, branch="main", id_=None, jobs=None):
    """One run record in the shape of the Actions runs API. `jobs`, when given, is the run's jobs read (the jobs API's list)."""
    record = {"id": id_ if id_ is not None else next(_ids), "path": path, "event": event, "status": status,
              "conclusion": conclusion, "head_sha": sha, "head_branch": branch, "created_at": created}
    if jobs is not None:
        record["jobs"] = jobs
    return record


def job(name, conclusion="success", status="completed"):
    """One job of a run, in the shape of the jobs API."""
    return {"name": name, "status": status, "conclusion": conclusion if status == "completed" else None}


def proven(sha=HEAD, created=LATE, id_=None):
    """A push run the push skip proved: push-skip succeeded, scope was skipped, and every suite job was skipped."""
    jobs = [job("push-skip"), job("scope", "skipped"), job("checks", "skipped"), job("checks-windows-merge-3", "skipped")]
    return run("push", sha=sha, created=created, id_=id_, jobs=jobs)


def linux_only(sha=HEAD, created=LATE, id_=None):
    """A push run that ran the Linux fast suites and nothing else: push-skip said run, scope ran, the daily-only jobs were skipped."""
    jobs = [job("push-skip"), job("scope"), job("checks"), job("checks-windows-merge-3", "skipped")]
    return run("push", sha=sha, created=created, id_=id_, jobs=jobs)


def run_in_process(env, api_get):
    """The gate's main() in this process, with `api_get` standing in for the live read. A read error that escapes main() comes
    back as rc 1 and the escaped type named in the text, which is what an uncaught exception does to the step's exit status."""
    spec = importlib.util.spec_from_file_location("nightly_skip_under_test", SKIP)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    buf = io.StringIO()
    with mock.patch.object(module, "api_get", api_get), contextlib.redirect_stdout(buf):
        try:
            rc = module.main(env)
        except Exception as ex:  # the uncaught read error the gate must never let out
            return 1, buf.getvalue() + "escaped main(): %s: %s" % (type(ex).__name__, ex)
    return rc, buf.getvalue()


def run_skip(runs=None, raw=None, head=HEAD, token=None, run_id=None, api_get=None):
    """Run the gate once on a stand-in read. Returns a dict: rc, value (the one skip value, or None), text (stdout and stderr) and
    summary (the step summary the gate wrote, '' when none). With `api_get`, the live read runs in this process with that
    function in place of the API call; without it, the gate runs as a subprocess on RUNS_JSON or no read."""
    folder = os.path.join(RUN_FOLDER, uuid.uuid4().hex)
    os.makedirs(folder)
    out, summary = os.path.join(folder, "output"), os.path.join(folder, "summary.md")
    env = {k: v for k, v in os.environ.items() if k not in STRIPPED}
    env["GITHUB_OUTPUT"] = out
    env["GITHUB_STEP_SUMMARY"] = summary
    env["REPO"] = "owner/repo"
    if raw is not None:
        env["RUNS_JSON"] = raw
    elif runs is not None:
        env["RUNS_JSON"] = json.dumps(runs)
    if head is not None:
        env["HEAD_SHA"] = head
    if token is not None:
        env["GH_TOKEN"] = token
    if run_id is not None:
        env["GITHUB_RUN_ID"] = str(run_id)
    if api_get is None:
        done = subprocess.run([sys.executable, SKIP], env=env, capture_output=True, text=True, timeout=60)
        rc, text = done.returncode, done.stdout + done.stderr
    else:
        rc, text = run_in_process(env, api_get)
    skips = []
    if os.path.isfile(out):
        with open(out, encoding="utf-8") as f:
            skips = [line.strip()[len("skip="):] for line in f if line.startswith("skip=")]
    text_summary = ""
    if os.path.isfile(summary):
        with open(summary, encoding="utf-8") as f:
            text_summary = f.read()
    return {"rc": rc, "value": skips[0] if len(skips) == 1 else None, "text": text, "summary": text_summary}


class NightlySkip(unittest.TestCase):
    def nightly_skip(self, **kwargs):
        self.assertTrue(os.path.isfile(SKIP), SKIP_MISSING)
        got = run_skip(**kwargs)
        self.assertEqual(got["rc"], 0, "the gate exits %d, so the nightly job fails on the gate: %s" % (got["rc"], got["text"][-300:]))
        return got["value"], got["text"]

    # Re-pointed (owner page item 880, 11:53 CST Nov 15): a push run counts for the skip only when its jobs prove it. The old
    # case gave skip=true on a green push run with no jobs, which the daily now has to cover.
    def test_skip_true_when_the_push_run_after_the_green_nightly_is_proven(self):
        value, _ = self.nightly_skip(runs=[run("schedule", created=OLDER), proven(created=LATE)])
        self.assertEqual(value, "true", "a proven push run after the green nightly, at main's head, must give skip=true")

    def test_skip_false_when_the_newest_nightly_failed(self):
        value, _ = self.nightly_skip(runs=[run("push"), run("schedule", created=OLDER), run("schedule", conclusion="failure")])
        self.assertEqual(value, "false", "a failed newest nightly must give skip=false")

    def test_the_newest_nightly_is_picked_by_created_time_not_by_list_order(self):
        value, _ = self.nightly_skip(runs=[run("schedule", conclusion="failure", created=NEWER), proven(created=MID),
                                   run("schedule", created=OLDER)])
        self.assertEqual(value, "false", "the newest nightly by created_at failed, so skip=false, whatever the list order")

    def test_skip_false_when_the_push_run_is_for_another_sha(self):
        value, _ = self.nightly_skip(runs=[run("push", sha=OTHER), run("schedule")])
        self.assertEqual(value, "false", "a green push run for another sha is not main's head, so skip=false")

    def test_skip_false_when_the_push_run_on_main_failed(self):
        value, _ = self.nightly_skip(runs=[run("push", conclusion="failure"), run("schedule")])
        self.assertEqual(value, "false", "a failed push run on main must give skip=false")

    def test_skip_false_when_the_push_run_is_not_on_main(self):
        value, _ = self.nightly_skip(runs=[run("push", branch="ci-batch"), run("schedule")])
        self.assertEqual(value, "false", "a push run on another branch is not main's push run, so skip=false")

    def test_skip_false_when_the_green_push_run_is_another_workflow(self):
        value, _ = self.nightly_skip(runs=[run("push", path=".github/workflows/other.yml"), run("schedule")])
        self.assertEqual(value, "false", "a green push run of another workflow is not checks.yml, so skip=false")

    # Re-pointed (owner page item 880, 11:53 CST Nov 15): the failure class is "skips on an in-progress daily". Another daily still
    # going is unknown, so the older green one does not decide. This run's own record is the case below.
    def test_an_in_progress_nightly_from_another_run_blocks_the_skip(self):
        value, _ = self.nightly_skip(runs=[proven(created=MID), run("schedule", created=OLDER),
                                   run("schedule", status="in_progress", id_=SELF_RUN + 1, created=LATE)])
        self.assertEqual(value, "false", "another daily still going is unknown, so skip=false, whatever the green one before it says")

    def test_this_runs_own_in_progress_record_does_not_block_the_skip(self):
        value, _ = self.nightly_skip(runs=[run("schedule", created=OLDER), proven(created=LATE),
                                   run("schedule", status="in_progress", id_=SELF_RUN, created=LATE)], run_id=SELF_RUN)
        self.assertEqual(value, "true", "the run that is deciding is in progress by definition, so its own record must not block")

    def test_skip_false_when_no_nightly_has_completed(self):
        value, _ = self.nightly_skip(runs=[run("push"), run("schedule", status="in_progress", conclusion=None)])
        self.assertEqual(value, "false", "with no completed nightly the gate has no green nightly, so skip=false")

    def test_skip_false_on_an_empty_run_list(self):
        value, _ = self.nightly_skip(runs=[])
        self.assertEqual(value, "false", "an empty run list has no push run on main, so skip=false")

    # Re-pointed (owner page item 880, 11:53 CST Nov 15): a full page holding the green push run and nightly still gives skip=true,
    # with the push run proven.
    def test_full_size_list_with_the_proven_push_run_and_nightly_gives_skip_true(self):
        full = [run("pull_request", sha=OTHER, created=OLDER) for _ in range(PAGE - 2)]
        value, _ = self.nightly_skip(runs=full + [proven(created=LATE), run("schedule", created=OLDER)])
        self.assertEqual(value, "true", "a hundred-run list that holds the proven push run and the green nightly must give skip=true")

    def test_full_size_list_without_a_green_push_run_on_main_gives_skip_false(self):
        full = [run("pull_request", sha=OTHER, created=OLDER) for _ in range(PAGE - 1)]
        value, _ = self.nightly_skip(runs=full + [run("schedule")])
        self.assertEqual(value, "false", "a hundred-run list with no push run on main must give skip=false")

    def test_a_read_that_is_not_json_gives_skip_false_and_says_unknown(self):
        value, text = self.nightly_skip(raw="not json")
        self.assertEqual(value, "false", "a read that fails must give skip=false")
        self.assertIn("unknown", text.lower(), "a read that fails must say unknown")

    def test_a_read_that_is_not_a_list_gives_skip_false_and_says_unknown(self):
        value, text = self.nightly_skip(raw='{"workflow_runs": []}')
        self.assertEqual(value, "false", "a runs read of the wrong shape must give skip=false")
        self.assertIn("unknown", text.lower(), "a runs read of the wrong shape must say unknown")

    def test_no_head_sha_gives_skip_false_and_says_unknown(self):
        value, text = self.nightly_skip(runs=[proven(created=LATE), run("schedule")], head=None)
        self.assertEqual(value, "false", "without a head sha the gate cannot judge main, so skip=false")
        self.assertIn("unknown", text.lower(), "without a head sha the gate must say unknown")

    def test_no_stand_in_and_no_token_gives_skip_false_and_says_unknown(self):
        value, text = self.nightly_skip(token=None)
        self.assertEqual(value, "false", "with no runs read and no token the gate must give skip=false")
        self.assertIn("unknown", text.lower(), "with no runs read and no token the gate must say unknown")


class NightlySkipFailureClasses(unittest.TestCase):
    """One case per failure class of the skip predicate (outcomes-tests-are-statements). Each feeds fake runs and jobs reads
    to the gate, and each expects skip=false. A case is named by the mistake it would let through."""

    def value(self, runs, **kwargs):
        self.assertTrue(os.path.isfile(SKIP), SKIP_MISSING)
        got = run_skip(runs=runs, **kwargs)
        self.assertEqual(got["rc"], 0, "the gate exits %d: %s" % (got["rc"], got["text"][-300:]))
        return got["value"]

    def test_an_unproven_push_run_after_the_green_nightly_does_not_skip(self):
        # Mistake: the daily skips a push that ran only the Linux fast suites, so no Windows or mutation leg covers it.
        self.assertEqual(self.value([run("schedule", created=OLDER), linux_only(created=LATE)]), "false",
                         "a push run whose scope ran is not proven, so the daily must run everything")

    def test_a_push_run_whose_push_skip_failed_does_not_skip(self):
        # Mistake: a failed push-skip job reads as proof, because the scope job was skipped anyway.
        jobs = [job("push-skip", "failure"), job("scope", "skipped"), job("checks", "skipped")]
        self.assertEqual(self.value([run("schedule", created=OLDER), run("push", created=LATE, jobs=jobs)]), "false",
                         "a push-skip job that failed proves nothing, so skip=false")

    def test_a_push_run_whose_jobs_were_not_read_does_not_skip(self):
        # Mistake: a push run with no jobs read is treated as proven, since nothing says otherwise.
        self.assertEqual(self.value([run("schedule", created=OLDER), run("push", created=LATE)]), "false",
                         "a push run with no jobs read is unproven, so skip=false")

    def test_a_red_push_run_after_the_green_nightly_does_not_skip_even_with_a_proven_newest_push(self):
        # Mistake: the newest push run is proven and green, so an older red push run after the green nightly goes unseen.
        self.assertEqual(self.value([run("schedule", created=OLDER), run("push", sha=OTHER, conclusion="failure", created=MID),
                                   proven(created=LATE)]), "false",
                         "a red push run after the green nightly is judged, so skip=false")

    def test_a_push_run_still_going_after_the_green_nightly_does_not_skip(self):
        # Mistake: the proven push run before it is taken as the verdict while a newer push run is still going.
        self.assertEqual(self.value([run("schedule", created=OLDER), proven(created=MID),
                                   run("push", status="in_progress", conclusion=None, created=LATE)]), "false",
                         "a push run still going after the green nightly is unknown, so skip=false")

    def test_a_newer_proven_push_run_at_another_sha_does_not_skip(self):
        # Mistake: main moved after this run's head, and the proof of the older head is taken for the new head.
        self.assertEqual(self.value([run("schedule", created=OLDER), proven(sha=HEAD, created=MID), proven(sha=OTHER, created=LATE)]),
                         "false", "the newest push run is at another sha, so main's head is not proven and skip=false")

    def test_a_cancelled_newest_nightly_does_not_skip(self):
        # Mistake: a cancelled daily reads as no daily, so the green one before it decides.
        self.assertEqual(self.value([run("schedule", created=OLDER), proven(created=MID), run("schedule", conclusion="cancelled", created=LATE)]),
                         "false", "a cancelled newest nightly is not green, so skip=false")

    def test_a_full_page_of_push_runs_that_does_not_reach_the_green_nightly_does_not_skip(self):
        # Mistake: the page is full, so the pushes between the green nightly and the page's oldest run are never read.
        full = [proven(sha=HEAD, created=LATE) for _ in range(PAGE)]
        self.assertEqual(self.value([run("schedule", created=OLDER)] + full), "false",
                         "a full page of push runs that ends newer than the green nightly hides pushes after it, so skip=false")

    def test_a_full_page_of_push_runs_that_reaches_the_green_nightly_can_skip(self):
        # Control, green on the old code: the same full page, with its oldest run before the green nightly, reaches it.
        full = [proven(sha=HEAD, created=LATE) for _ in range(PAGE - 1)] + [linux_only(sha=OTHER, created=BEFORE)]
        self.assertEqual(self.value([run("schedule", created=OLDER)] + full), "true",
                         "a full page whose oldest run is before the green nightly reaches it, so the proven head can skip")

    def test_a_red_push_run_before_the_green_nightly_is_not_judged(self):
        # Control, green on the old code: a push run before the green daily is covered by that daily, so it does not block.
        self.assertEqual(self.value([run("push", sha=OTHER, conclusion="failure", created=BEFORE), run("schedule", created=MID),
                                   proven(created=LATE)]), "true",
                         "a red push run before the green nightly is covered by it, so the proven head can skip")



class NightlySkipRange(unittest.TestCase):
    """Design item 4 (owner page item 880, 11:53 CST Nov 15): a schedule run prints the range it covers, in the log and in the
    step summary. The range runs from the last green daily's head to this head, and counts the push runs after that daily."""

    def test_the_range_line_names_the_green_daily_head_this_head_and_the_merges_after_it(self):
        # Named failure: the gate prints no range line, so the daily's log and summary hold no record of what it covers.
        got = run_skip(runs=[run("schedule", created=OLDER, sha=OTHER), proven(sha=MERGE, created=MID), proven(sha=HEAD, created=LATE)])
        want = "range: %s..%s (2 merges)" % (OTHER, HEAD)
        self.assertIn(want, got["text"], "the log has no range line naming the green daily, this head and the 2 push runs after it")
        self.assertIn(want, got["summary"], "the step summary has no range line naming the green daily, this head and the 2 push runs after it")

    def test_the_range_line_counts_no_push_run_from_before_the_green_daily(self):
        # Named failure: the count takes every push run, so the push run before the green daily is counted too.
        got = run_skip(runs=[run("push", created=BEFORE, sha=MERGE), run("schedule", created=OLDER, sha=HEAD)])
        self.assertIn("range: %s..%s (0 merges)" % (HEAD, HEAD), got["text"], "a push run before the green daily is in the range")

    def test_the_range_line_says_unknown_with_no_green_daily(self):
        # Named failure: a daily with no green one before it prints a range from nothing, not the unknown line.
        got = run_skip(runs=[run("schedule", conclusion="failure", created=OLDER), proven(created=MID)])
        self.assertIn("range: unknown (no green daily)", got["text"], "a run with no green daily must print the unknown range line")
        self.assertIn("range: unknown (no green daily)", got["summary"], "the unknown range line must reach the step summary too")


class NightlySkipJobWiring(unittest.TestCase):
    """The skip job is an ancestor of every job through scope. A job-level `if` skips it on a pull request or a push,
    and a skipped ancestor skips every job behind scope, so all-jobs-passed fails on every PR run."""

    def test_skip_job_has_no_job_level_if(self):
        text = open(os.path.join(ROOT, WORKFLOW), encoding="utf-8").read()
        start = text.index("\n  nightly-skip:\n")
        end = text.index("\n  # ", start + 1)
        job_text = text[start:end]
        header = job_text.split("    steps:", 1)[0]
        self.assertNotIn("\n    if:", header,
                         "nightly-skip must run on every event: a skipped job it leaves behind skips scope's descendants")


class NightlySkipReadErrors(unittest.TestCase):
    """A read error on the live path is unknown, never a crash. The gate's contract (its docstring): it exits 0 on every path,
    writes skip=false and says unknown. The stand-in raises what a read can raise and urllib does not wrap:
    http.client.IncompleteRead (a body cut short; not an OSError) and any other Exception (owner page item 880, 11:53 CST
    Nov 15). The stand-in records each URL, so a case first shows the read it means was reached, then judges the outcome."""

    def gate(self, errors):
        """Run the gate on the live read, with the reads named in `errors` raising. -> (result, the URLs requested)."""
        urls = []

        def api_get(url, token):
            urls.append(url)
            if "/jobs?" in url:
                if "jobs" in errors:
                    raise errors["jobs"]
                return {"jobs": [job("push-skip"), job("scope", "skipped")]}
            if "runs" in errors:
                raise errors["runs"]
            query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            if int(query.get("page", ["1"])[0]) > 1:
                return {"workflow_runs": []}
            served = [run("schedule", created=OLDER), run("push", created=LATE)]  # the push run has no jobs: the jobs read decides it
            return {"workflow_runs": [r for r in served if r["event"] == query["event"][0]]}

        got = run_skip(token="t", run_id=SELF_RUN, api_get=api_get)
        return got, urls

    def assert_reached(self, urls, fragment, read):
        self.assertTrue(any(fragment in u for u in urls), "scope: the %s read was never requested, so the case proves nothing" % read)

    def assert_unknown(self, got, read):
        self.assertEqual(got["rc"], 0, "the gate exits %d when the %s read raises, so the nightly step goes red: %s"
                         % (got["rc"], read, got["text"][-300:]))
        self.assertEqual(got["value"], "false", "a %s read that raises must give skip=false" % read)
        self.assertIn("unknown", got["text"].lower(), "a %s read that raises must say unknown in the log" % read)

    def test_an_incomplete_read_of_the_runs_list_is_unknown_not_a_crash(self):
        # Mistake: runs_page catches URLError, OSError and ValueError only, and http.client.IncompleteRead is none of them.
        got, urls = self.gate({"runs": http.client.IncompleteRead(b"")})
        self.assert_reached(urls, "event=schedule", "runs")
        self.assert_unknown(got, "runs")

    def test_a_runtime_error_on_the_runs_list_is_unknown_not_a_crash(self):
        # Mistake: any Exception other than the three runs_page catches escapes main() as a traceback and exit 1.
        got, urls = self.gate({"runs": RuntimeError("the runs read broke")})
        self.assert_reached(urls, "event=schedule", "runs")
        self.assert_unknown(got, "runs")

    def test_an_incomplete_read_of_a_jobs_list_is_unknown_not_a_crash(self):
        # Mistake: jobs_reader catches the same three, so a push run's jobs read cut short escapes main() the same way.
        got, urls = self.gate({"jobs": http.client.IncompleteRead(b"")})
        self.assert_reached(urls, "/jobs?", "jobs")
        self.assert_unknown(got, "jobs")

    def test_a_runtime_error_on_a_jobs_list_is_unknown_not_a_crash(self):
        # Mistake: an Exception from the jobs read, past jobs_reader's three catches, escapes proven() and main().
        got, urls = self.gate({"jobs": RuntimeError("the jobs read broke")})
        self.assert_reached(urls, "/jobs?", "jobs")
        self.assert_unknown(got, "jobs")

    def test_control_a_url_error_on_the_runs_list_is_already_unknown(self):
        # Control, green on the old code: URLError is one of the three runs_page catches, so this read is already unknown.
        got, urls = self.gate({"runs": urllib.error.URLError("unreachable")})
        self.assert_reached(urls, "event=schedule", "runs")
        self.assert_unknown(got, "runs")


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


if __name__ == "__main__":
    unittest.main()
