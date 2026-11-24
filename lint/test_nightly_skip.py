#!/usr/bin/env python3
"""Tests for .github/scripts/nightly-skip.py, the step that lets the daily scheduled run skip.

The gate writes skip=true to $GITHUB_OUTPUT only when every one of these holds (owner, 13:44 CST Nov 23, answer a to Q5):
  (a) the newest schedule run of checks.yml, other than this run, is completed and succeeded, and no other schedule
      run is still going;
  (b) no push run of checks.yml on main was created after that green daily: main has not moved since it. A push run
      after it gives skip=false whether or not the push skip proved it, since a push never runs the Windows shards;
  (c) the newest push run of checks.yml on main, if there is one, has this run's head sha, and the green daily's head is
      this run's head (owner pick on item 893, relayed 14:14 CST Nov 15: a day main did not move skips);
  (d) the push runs read reach the green daily: a full page of push runs (100) must not end newer than it.
Any read failure writes skip=false and says "unknown".

The gate also prints the range line, `range: <green daily head>..<this head> (<N> merges)`, to stdout and to
$GITHUB_STEP_SUMMARY, where N counts the push runs created after the green daily; `range: unknown (no green daily)`
when there is none.

RUNS_JSON is the stand-in for the runs read: a JSON list of run records in the shape of the Actions runs API, with a
`jobs` list in the shape of the jobs API on each push run. GITHUB_RUN_ID is this run; its own record does not block.
The test never reaches the network.

    python3 lint/test_nightly_skip.py
"""
import contextlib
from datetime import datetime, timedelta
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


def narrowed_push(sha=HEAD, created=LATE, id_=None):
    """A push run the push skip proved after a narrowed pull request: push-skip succeeded, scope was skipped, and the Windows merge
    shard the narrowed run left out was skipped with it."""
    jobs = [job("push-skip"), job("scope", "skipped"), job("checks-windows-merge-3", "skipped")]
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


def pushes_since(count):
    """`count` push runs on main after OLDER, newest first. The newest is at HEAD and each other has its own sha, so a page of them
    is a real page of merges. Created times climb one minute each, so no two tie."""
    base = datetime(2026, 11, 10)
    out = []
    for i in range(count - 1, -1, -1):
        stamp = (base + timedelta(minutes=i)).strftime("%Y-%m-%dT%H:%M:%SZ")
        out.append(run("push", sha=HEAD if i == count - 1 else "%040x" % (0x100 + i), created=stamp))
    return out


def live_run_skip(pages, errors=None):
    """Run the skip's live read once. `pages` maps an event to its pages, each a list of run records: page n of an event is served
    for `page=n`, and a page past the list is empty. `errors` maps `runs` or `jobs` to an exception that read raises. A push run
    with no `jobs` key has its jobs read from the stand-in, which reports a push skip that proved it. -> (result, the URLs requested)."""
    urls = []
    errors = errors or {}

    def api_get(url, token):
        urls.append(url)
        if "/jobs?" in url:
            if "jobs" in errors:
                raise errors["jobs"]
            return {"jobs": [job("push-skip"), job("scope", "skipped")]}
        if "runs" in errors:
            raise errors["runs"]
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        number = int(query.get("page", ["1"])[0])
        served = pages.get(query["event"][0], [])
        return {"workflow_runs": served[number - 1] if number <= len(served) else []}

    return run_skip(token="t", run_id=SELF_RUN, api_get=api_get), urls


def requested_pages(urls, event):
    """The page numbers one event's reads asked for, sorted. A read with no page parameter is page 1."""
    pages = []
    for url in urls:
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        if query.get("event") == [event]:
            pages.append(int(query.get("page", ["1"])[0]))
    return sorted(pages)


class NightlySkip(unittest.TestCase):
    def nightly_skip(self, **kwargs):
        self.assertTrue(os.path.isfile(SKIP), SKIP_MISSING)
        got = run_skip(**kwargs)
        self.assertEqual(got["rc"], 0, "the gate exits %d, so the nightly job fails on the gate: %s" % (got["rc"], got["text"][-300:]))
        return got["value"], got["text"]

    # Owner, 13:44 CST Nov 23, answer a to Q5: the daily skips only while main has not moved since the last green daily. A push run
    # the push skip proved still moved main, so the daily runs everything.
    def test_skip_false_when_a_proven_push_run_follows_the_green_nightly(self):
        value, _ = self.nightly_skip(runs=[run("schedule", created=OLDER), proven(created=LATE)])
        self.assertEqual(value, "false", "a proven push run after the green nightly moved main, so skip=false (owner, 13:44 CST Nov 23, Q5 a)")

    # Owner, 13:44 CST Nov 23, answer a to Q5: the newest push run is not the only one that counts. A proven push run between the
    # green nightly and this head also moved main, so skip=false.
    def test_skip_false_when_an_earlier_proven_push_run_follows_the_green_nightly(self):
        value, _ = self.nightly_skip(runs=[run("schedule", created=OLDER, sha=OTHER), proven(sha=MERGE, created=MID),
                                   proven(sha=HEAD, created=LATE)])
        self.assertEqual(value, "false", "a proven push run between the green nightly and this head moved main, so skip=false "
                         "(owner, 13:44 CST Nov 23, Q5 a)")

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

    # Re-pointed (owner pick on item 893, relayed 14:14 CST Nov 15): the push run is created after the green daily, so it is judged and not
    # skipped as a day with no push since. The claim is unchanged: a failed push run on main must give skip=false.
    def test_skip_false_when_the_push_run_on_main_failed(self):
        value, _ = self.nightly_skip(runs=[run("push", conclusion="failure", created=LATE), run("schedule")])
        self.assertEqual(value, "false", "a failed push run on main must give skip=false")

    # Re-pointed (owner pick on item 893, relayed 14:14 CST Nov 15): the daily sits on an older head, so a day main did not move cannot
    # skip on it. The claim is unchanged: a push run on another branch is not main's push run, so this head is not proven.
    def test_skip_false_when_the_push_run_is_not_on_main(self):
        value, _ = self.nightly_skip(runs=[run("push", branch="ci-batch", created=LATE), run("schedule", sha=OTHER)])
        self.assertEqual(value, "false", "a push run on another branch is not main's push run, so skip=false")

    # Re-pointed (owner pick on item 893, relayed 14:14 CST Nov 15): the daily sits on an older head, so the other workflow's push at this
    # head is the only thing that could cover it. The claim is unchanged: a green push run of another workflow is not checks.yml.
    def test_skip_false_when_the_green_push_run_is_another_workflow(self):
        value, _ = self.nightly_skip(runs=[run("push", path=".github/workflows/other.yml", created=LATE), run("schedule", sha=OTHER)])
        self.assertEqual(value, "false", "a green push run of another workflow is not checks.yml, so skip=false")

    # Re-pointed (owner page item 880, 11:53 CST Nov 15): the failure class is "skips on an in-progress daily". Another daily still
    # going is unknown, so the older green one does not decide. This run's own record is the case below.
    def test_an_in_progress_nightly_from_another_run_blocks_the_skip(self):
        value, _ = self.nightly_skip(runs=[proven(created=MID), run("schedule", created=OLDER),
                                   run("schedule", status="in_progress", id_=SELF_RUN + 1, created=LATE)])
        self.assertEqual(value, "false", "another daily still going is unknown, so skip=false, whatever the green one before it says")

    # Re-shaped (owner, 13:44 CST Nov 23, answer a to Q5): main has not moved since the green daily, so the skip holds and only this
    # run's own record is under test. The push run that was here moved main, so it is gone.
    def test_this_runs_own_in_progress_record_does_not_block_the_skip(self):
        value, _ = self.nightly_skip(runs=[run("schedule", created=OLDER),
                                   run("schedule", status="in_progress", id_=SELF_RUN, created=LATE)], run_id=SELF_RUN)
        self.assertEqual(value, "true", "the run that is deciding is in progress by definition, so its own record must not block")

    def test_skip_false_when_no_nightly_has_completed(self):
        value, _ = self.nightly_skip(runs=[run("push"), run("schedule", status="in_progress", conclusion=None)])
        self.assertEqual(value, "false", "with no completed nightly the gate has no green nightly, so skip=false")

    def test_skip_false_on_an_empty_run_list(self):
        value, _ = self.nightly_skip(runs=[])
        self.assertEqual(value, "false", "an empty run list has no push run on main, so skip=false")

    # Owner, 13:44 CST Nov 23, answer a to Q5: a full list that holds a proven push run after the green nightly moved main, so skip=false.
    def test_full_size_list_with_a_proven_push_run_after_the_nightly_gives_skip_false(self):
        full = [run("pull_request", sha=OTHER, created=OLDER) for _ in range(PAGE - 2)]
        value, _ = self.nightly_skip(runs=full + [proven(created=LATE), run("schedule", created=OLDER)])
        self.assertEqual(value, "false", "a hundred-run list whose proven push run follows the green nightly must give skip=false "
                         "(owner, 13:44 CST Nov 23, Q5 a)")

    # Re-pointed (owner pick on item 893, relayed 14:14 CST Nov 15): main has not moved since the green daily at this head, so the day
    # skips. The old expectation required a full run on that day, which the pick rules out.
    def test_full_size_list_with_no_push_since_the_green_daily_at_this_head_gives_skip_true(self):
        full = [run("pull_request", sha=OTHER, created=OLDER) for _ in range(PAGE - 1)]
        value, _ = self.nightly_skip(runs=full + [run("schedule")])
        self.assertEqual(value, "true", "a green daily at this head with no push run on main after it must give skip=true (item 893)")

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


    # Owner pick on item 893, relayed 14:14 CST Nov 15: the daily fires only on a day when main moved. A green daily at this run's head
    # with no push run after it skips, since that head already ran every slow leg green. Red on the old code, which required a push run.
    def test_a_green_daily_at_this_head_with_no_push_since_skips(self):
        value, _ = self.nightly_skip(runs=[run("schedule", created=OLDER)])
        self.assertEqual(value, "true", "a green daily at this head with no push run after it must give skip=true (item 893)")

    def test_a_green_daily_at_this_head_after_a_push_at_this_head_skips(self):
        # The push run at this head came before the daily, so the daily already covers it (item 893).
        value, _ = self.nightly_skip(runs=[run("push", created=MID), run("schedule", created=LATE)])
        self.assertEqual(value, "true", "a push run at this head before a green daily at this head is covered by that daily (item 893)")

    def test_a_green_daily_at_another_head_with_no_push_since_does_not_skip(self):
        # Mix, owner pick on item 893: exact head equality is the only route to a skip with no push since. A green daily at another
        # head with nothing after it leaves this head unknown, whether or not a push run at this head came before it.
        cases = {
            "no push run at all": [run("schedule", created=OLDER, sha=OTHER)],
            "a push run at this head before the daily": [run("push", created=BEFORE), run("schedule", created=OLDER, sha=OTHER)],
        }
        for name, runs in cases.items():
            with self.subTest(case=name):
                value, text = self.nightly_skip(runs=runs)
                self.assertEqual(value, "false", "a green daily at another head with no push run after it leaves this head unknown: %s"
                                 % text[-200:])

    def test_a_newest_push_at_another_head_with_a_green_daily_at_this_head_does_not_skip(self):
        # Mix, owner pick on item 893: the newest push run on main must be at this head before the no-push skip can apply.
        value, _ = self.nightly_skip(runs=[run("push", sha=OTHER, created=BEFORE), run("schedule", created=OLDER)])
        self.assertEqual(value, "false", "the newest push run on main is at another head, so this head is not proven and skip=false")


class NightlySkipFailureClasses(unittest.TestCase):
    """One case per failure class of the skip predicate (outcomes-tests-are-statements). Each feeds fake runs and jobs reads
    to the gate, and each expects skip=false. A case is named by the mistake it would let through."""

    def value(self, runs, **kwargs):
        self.assertTrue(os.path.isfile(SKIP), SKIP_MISSING)
        got = run_skip(runs=runs, **kwargs)
        self.assertEqual(got["rc"], 0, "the gate exits %d: %s" % (got["rc"], got["text"][-300:]))
        return got["value"]

    def test_a_daily_at_this_head_that_is_not_green_does_not_skip_with_no_push_since(self):
        # Keep, owner pick on item 893: the no-push skip needs a green daily. A red or cancelled daily at this head is no proof.
        for conclusion in ("failure", "cancelled"):
            with self.subTest(conclusion=conclusion):
                self.assertEqual(self.value([run("schedule", conclusion=conclusion, created=OLDER)]), "false",
                                 "a %s daily at this head is not green, so skip=false with no push run after it" % conclusion)

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
        # Control, green on the old code (owner, 13:44 CST Nov 23, Q5 a): a full page of 100 pushes, all before the green nightly at
        # this head, reaches it, and main has not moved since. Each push run is before the nightly, so none counts as a move.
        full = pushes_since(PAGE)
        self.assertEqual(self.value([run("schedule", created=NEWER)] + full), "true",
                         "a full page whose oldest run is before the green nightly reaches it, so the no-push skip can read it")

    def test_a_red_push_run_before_the_green_nightly_is_not_judged(self):
        # Control, green on the old code (owner, 13:44 CST Nov 23, Q5 a): a red push run before the green daily is covered by that
        # daily and moved nothing after it, so the daily at this head can skip.
        self.assertEqual(self.value([run("push", sha=OTHER, conclusion="failure", created=BEFORE), run("push", sha=HEAD, created=MID),
                                   run("schedule", created=LATE)]), "true",
                         "a red push run before the green nightly is covered by it, so the no-push skip at this head can apply")


class NightlySkipNarrowedPush(unittest.TestCase):
    """The daily may skip after a push the push skip proved, while main has not moved past that push. A narrowed push runs none of
    the Windows shards it leaves out, so a daily that skips after one runs those shards on no tree of main."""

    def test_a_daily_skips_when_main_has_not_moved_past_a_narrowed_push(self):
        # Control, green on the old code: main is unmoved since the green daily, and the narrowed push sits at that head before it.
        got = run_skip(runs=[narrowed_push(sha=OTHER, created=BEFORE), run("schedule", sha=OTHER, created=OLDER)], head=OTHER)
        self.assertEqual(got["rc"], 0, "the gate exits %d: %s" % (got["rc"], got["text"][-300:]))
        self.assertEqual(got["value"], "true", "the daily does not skip with main unmoved since the green daily: %s" % got["text"][-300:])

    def test_a_daily_does_not_skip_after_a_narrowed_push_moved_main(self):
        push = narrowed_push(sha=HEAD, created=LATE)
        runs = [run("schedule", sha=OTHER, created=OLDER), push]
        # Scope first: the push is at a new head, and its own jobs show it was proven and that a Windows shard was left out.
        jobs = {j["name"]: j["conclusion"] for j in push["jobs"]}
        self.assertNotEqual(push["head_sha"], OTHER, "the push did not move main past the green daily")
        self.assertEqual(jobs.get("push-skip"), "success", "the push was not proven by the push skip: %s" % jobs)
        self.assertEqual(jobs.get("checks-windows-merge-3"), "skipped", "the push ran the Windows merge shard: %s" % jobs)
        got = run_skip(runs=runs, head=HEAD)
        self.assertEqual(got["rc"], 0, "the gate exits %d: %s" % (got["rc"], got["text"][-300:]))
        self.assertEqual(got["value"], "false", "the daily skips after main moved past a push that left a Windows shard out: %s"
                         % got["text"][-300:])


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


    def test_the_range_line_says_at_least_when_the_live_read_fills_five_pages_and_never_reaches_the_daily(self):
        # Named failure: the range line prints the 500 push runs the live read holds as an exact count, though the read stopped at its
        # five-page limit and never reached the green daily, which is older still. Floor condition: the push read is full and its
        # oldest run is newer than the daily, so the count is at least what was read (wording: `at least N merges`).
        daily = run("schedule", created=OLDER, sha=OTHER)
        pushes = pushes_since(5 * PAGE)
        pages = {"schedule": [[daily]], "push": [pushes[i:i + PAGE] for i in range(0, len(pushes), PAGE)]}
        got, urls = live_run_skip(pages)
        read = requested_pages(urls, "push")
        self.assertIn(5, read, "scope: page 5 of the push runs was never requested, so the page limit is not what the case tests (read %r)" % read)
        self.assertNotIn(6, read, "scope: page 6 of the push runs was requested, past the five-page limit (read %r)" % read)
        self.assertIn("nightly-skip: unknown", got["text"], "scope: the decision did not reach the unknown path: %s" % got["text"][-300:])
        want = "range: %s..%s (at least 500 merges)" % (OTHER, HEAD)
        self.assertIn(want, got["text"], "the range line must say 'at least 500 merges' when the push read never reached the daily: %s"
                      % got["text"][:300])
        self.assertIn(want, got["summary"], "the step summary must carry the same 'at least 500 merges' range line")
        self.assertNotIn("(500 merges)", got["text"], "the range line claims an exact count of 500 merges, which a read that stopped early cannot know")

    def test_the_range_line_says_at_least_for_a_full_push_page_that_never_reaches_the_daily(self):
        # The same floor on the stand-in read: one full page of 100 push runs, all after the green daily, so the list does not reach it.
        got = run_skip(runs=[run("schedule", created=OLDER, sha=OTHER)] + pushes_since(PAGE))
        self.assertIn("nightly-skip: unknown", got["text"], "scope: the full page did not reach the unknown path: %s" % got["text"][-300:])
        want = "range: %s..%s (at least 100 merges)" % (OTHER, HEAD)
        self.assertIn(want, got["text"], "a full push page that does not reach the green daily must say 'at least 100 merges': %s"
                      % got["text"][:300])
        self.assertIn(want, got["summary"], "the step summary must carry the same 'at least 100 merges' range line")
        self.assertNotIn("(100 merges)", got["text"], "the range line claims an exact count of 100 merges on a page that does not reach the daily")


class NightlySkipLivePages(unittest.TestCase):
    """The live read past page 1, decided end to end (owner page item 880, 11:53 CST Nov 15). Page 1 is a full page of push runs since
    the green daily, the newest at this head. Page 2 holds one push run from before the daily: a short page that ends the read. A read
    stopped after page 1 sees a full page that does not reach the daily, so it says unknown and skips nothing."""

    # Owner, 13:44 CST Nov 23, answer a to Q5: the pushes since the daily moved main, so the decision is skip=false. The case keeps its
    # purpose: page two must be read to reach the daily, and the answer must be a decision, not an unknown.
    def test_skip_false_when_the_push_runs_since_the_daily_fill_page_one_and_page_two_reaches_it(self):
        daily = run("schedule", created=OLDER, sha=OTHER)
        pages = {"schedule": [[daily]], "push": [pushes_since(PAGE), [run("push", sha=MERGE, created=BEFORE)]]}
        got, urls = live_run_skip(pages)
        self.assertIn(2, requested_pages(urls, "push"), "scope: page two of the push runs was never requested, so the case proves nothing")
        self.assertEqual(got["rc"], 0, "the skip exits %d: %s" % (got["rc"], got["text"][-300:]))
        self.assertNotIn("nightly-skip: unknown", got["text"], "the read reached the daily, so the pushes since it are a decision: %s"
                         % got["text"][-300:])
        self.assertEqual(got["value"], "false", "the pushes since the daily, read through page two, moved main, so skip=false: %s"
                         % got["text"][-300:])


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

    def run_skip(self, errors):
        """Run the gate on the live read, with the reads named in `errors` raising. -> (result, the URLs requested)."""
        # The push run has no jobs: the jobs read decides it.
        served = {"schedule": [[run("schedule", created=OLDER)]], "push": [[run("push", created=LATE)]]}
        return live_run_skip(served, errors)

    def assert_reached(self, urls, fragment, read):
        self.assertTrue(any(fragment in u for u in urls), "scope: the %s read was never requested, so the case proves nothing" % read)

    def assert_unknown(self, got, read):
        self.assertEqual(got["rc"], 0, "the gate exits %d when the %s read raises, so the nightly step goes red: %s"
                         % (got["rc"], read, got["text"][-300:]))
        self.assertEqual(got["value"], "false", "a %s read that raises must give skip=false" % read)
        self.assertIn("unknown", got["text"].lower(), "a %s read that raises must say unknown in the log" % read)

    def test_an_incomplete_read_of_the_runs_list_is_unknown_not_a_crash(self):
        # Mistake: runs_page catches URLError, OSError and ValueError only, and http.client.IncompleteRead is none of them.
        got, urls = self.run_skip({"runs": http.client.IncompleteRead(b"")})
        self.assert_reached(urls, "event=schedule", "runs")
        self.assert_unknown(got, "runs")

    def test_a_runtime_error_on_the_runs_list_is_unknown_not_a_crash(self):
        # Mistake: any Exception other than the three runs_page catches escapes main() as a traceback and exit 1.
        got, urls = self.run_skip({"runs": RuntimeError("the runs read broke")})
        self.assert_reached(urls, "event=schedule", "runs")
        self.assert_unknown(got, "runs")

    def test_an_incomplete_read_of_a_jobs_list_is_unknown_not_a_crash(self):
        # Mistake: jobs_reader catches the same three, so a push run's jobs read cut short escapes main() the same way.
        got, urls = self.run_skip({"jobs": http.client.IncompleteRead(b"")})
        self.assert_reached(urls, "/jobs?", "jobs")
        self.assert_unknown(got, "jobs")

    def test_a_runtime_error_on_a_jobs_list_is_unknown_not_a_crash(self):
        # Mistake: an Exception from the jobs read, past jobs_reader's three catches, escapes proven() and main().
        got, urls = self.run_skip({"jobs": RuntimeError("the jobs read broke")})
        self.assert_reached(urls, "/jobs?", "jobs")
        self.assert_unknown(got, "jobs")

    def test_control_a_url_error_on_the_runs_list_is_already_unknown(self):
        # Control, green on the old code: URLError is one of the three runs_page catches, so this read is already unknown.
        got, urls = self.run_skip({"runs": urllib.error.URLError("unreachable")})
        self.assert_reached(urls, "event=schedule", "runs")
        self.assert_unknown(got, "runs")


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


if __name__ == "__main__":
    unittest.main()
