#!/usr/bin/env python3
"""Tests for the idle red pull request rule: a non-draft PR whose head is red and whose newest pull_request run is 2 hours old
or more goes back to draft. Its comment says why and how to return.

Run: python3 merge/test_idle_prs.py

WHAT IT PROVES. `merge --draft-idle` (the janitor's entry), run in-process through merge.main with IdleHost (no gh call). It lists the
open pull requests once, drafts each non-draft PR whose head is red and idle, posts one comment per drafted PR, and prints a summary
line with the count drafted. A failed read is unknown: that PR is left alone, and a failed list read drafts nothing and exits nonzero.
The clash hook (a red idle PR does not block `merge <n> --ready`) is in test_lane_lint.py, class ReadyChecks, beside the pre-ready
clash cases, and uses IdleHost from here.

A cloud host cannot draft: its route is printed, no comment says the PR returned to draft, and the PR is not counted as drafted, so a
clash still counts it. A draft that lands before a failed comment is reported as drafted, comment failed.

Host surface these cases pin (the names the builder implements; IdleHost is the fake of each):
  open_pulls()      one list read per sweep; REST rows of the open pulls
  runs(sha)         the pull_request runs of a head: name, status, conclusion, event, createdAt (ISO, GitHub's own field)
  head_state(n, sha) "red: <names>" for a completed failure, "pending: <names>" while a run is still going, "green" otherwise
  to_draft(n)       the local `gh pr ready <n> --undo`; a cloud host answers (False, merge.DRAFT_ROUTES)
  post_comment(n, body)  one comment per drafted PR
  server_now()      GitHub's clock in epoch seconds, from the Date header of the last REST reply; None when unread. The 2 h age is
                    judged on it, never on now()
  now()             the local clock. The 2 h age is never judged on it; a case moves it to show that

The clock is synthetic: every age is counted from test_merge.FAKE_NOW, so a module that reads the wall clock sees each fixture run
as weeks old and fails the 1 h 59 min and the newest-run cases. The 2-hour threshold is pinned by its edges (exactly 2 h drafts, one
second less does not), not by the module's constant name. GitHub's clock and the local clock both start at FAKE_NOW; a case moves one
of them to show which clock the age is read from.

The Date-header classes (GitHubDateHeader, GitHubDateZoneOffset, GitHubDateSweep) read GitHub's clock from a reply's Date header, as
Host does. Their ages count from DATE_EPOCH, the instant that header names, never from FAKE_NOW. GitHubDateHeader and GitHubDateZoneOffset
answer gh at merge.sh (the seam RateLimitWait.replies patches), so Host.gh and its header read run as in production. GitHubDateSweep
answers gh with the fake gh on PATH (test_merge.FAKE_GH_PR), so the subprocess call runs too.

Cost pin (CostHost, the real merge.Host with each gh call answered here, so every call that reaches gh is counted): one open-pulls read
per sweep. Per non-draft PR under a pinned requiredChecks list: one run list (memoized per head) and two checks page reads (check runs,
statuses). Under "none": the run list only, and no checks read. Per drafted PR: one `gh pr ready --undo` and one comment POST. A draft PR
is read for nothing. No file is written, and no timer is started.
Not pinned here: the required-names read (the ruleset, then the classic protection) that a non-list requiredChecks makes once per base, since
the pin names a list; a second page of check runs or statuses (each case answers one page); the gh retries of a network fault; and the
arguments of `gh pr ready --undo` past the PR number. A PR a person readies again with no push and that goes red and idle again is not
pinned either. The sweep then drafts it, and a second comment is not blocked by a comment read. That is an open design question for the
report, not a case.

Each case runs the sweep first, then asserts its outcome, so a must-not case is never a pass on a missing entry. Each failure message
names one cause.
"""
import calendar
import contextlib
import io
import itertools
import json
import os
import re
import sys
import time
import unittest
import unittest.mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import merge  # noqa: E402
import test_merge as tm  # noqa: E402  the FakeHost, the Env fixture and the fake REST rows (one home)

HOUR = 3600
IDLE_SECONDS = 2 * HOUR  # the ruling's threshold, written as the test's own value
RULING = "owner, 2026-11-23 10:54 CST"
RED_JOB = "Lint and tests"
RUN_IDS = itertools.count(9000)


def ago(seconds):
    """GitHub's createdAt for a run `seconds` before the fixture clock. The clock is tm.FAKE_NOW, never the real one."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(tm.FAKE_NOW - seconds))


def run(name, conclusion, status="completed", age=3 * HOUR, event="pull_request"):
    """One workflow run as `gh run list --json ...,createdAt` answers it."""
    rid = next(RUN_IDS)
    return {"name": name, "status": status, "conclusion": conclusion, "event": event, "createdAt": ago(age),
            "databaseId": rid, "workflowDatabaseId": rid}


def red(age=3 * HOUR, name=RED_JOB):
    return run(name, "failure", age=age)


def green(age=3 * HOUR):
    return run(RED_JOB, "success", age=age)


def pending(name, age=3 * HOUR):
    return run(name, None, status="in_progress", age=age)


def cancelled(age=3 * HOUR):
    return run(RED_JOB, "cancelled", age=age)


def sha_of(n):
    return "%040x" % n


class IdleHost(tm.FakeHost):
    """The fake GitHub half of the idle sweep and the clash hook. Scripted; no gh call.

    include_own: the open list keeps the lane's own pull request, as FakeHost lists it (the clash cases need it). A sweep does not.
    runs_by_sha: the runs a head reads as. A head with no entry falls through to FakeHost's own answers.
    runs_reads: each head runs() read, in order (the cost pin counts them).
    runs_fail: {sha: text}: a runs() read of that head raises merge.Stop with the text (unknown for that head).
    list_fail: the text the open-pulls read raises (unknown for the whole sweep).
    drafts: each n the local draft call drafted. draft_refuse: a cloud host, which cannot send the undo and answers the route.
    github_now: GitHub's clock, as server_now() answers it (None: unread). local_now: the clock now() answers.
    comment_fail: the text post_comment raises merge.Stop with (a comment that fails after the draft landed).
    """

    def __init__(self, root, other, branch="feat"):
        super().__init__(root, other, branch)
        self.pulls = {}
        self.include_own = False
        self.runs_by_sha, self.runs_reads, self.runs_fail = {}, [], {}
        self.list_fail = None
        self.drafts, self.draft_refuse = [], False
        self.github_now, self.local_now, self.comment_fail = tm.FAKE_NOW, tm.FAKE_NOW, None

    def now(self):
        return self.local_now

    def server_now(self):
        return self.github_now

    def post_comment(self, n, body):
        if self.comment_fail:
            raise merge.Stop(self.comment_fail)
        super().post_comment(n, body)

    @classmethod
    def adopt(cls, host):
        """The same host as an IdleHost: its scripted state stays, and the idle fakes start empty."""
        new = cls(host.root, host.other, host.branch)
        new.__dict__.update(host.__dict__)
        return new

    def open_pulls(self):
        if self.include_own:
            return super().open_pulls()
        self.pull_list_reads += 1
        if self.list_fail:
            raise merge.Stop(self.list_fail)
        return [row for row in self.pulls.values() if row["state"] == "open"]

    def pages(self, rel, key=None, fields=None):
        return self.open_pulls() if rel == "pulls" else []

    def runs(self, sha):
        self.runs_reads.append(sha)
        if sha in self.runs_fail:
            raise merge.Stop(self.runs_fail[sha])
        return [dict(r) for r in self.runs_by_sha.get(sha, [])]

    def head_state(self, n, sha=None):
        if sha not in self.runs_by_sha:
            return super().head_state(n, sha)
        rows = self.runs_by_sha[sha]
        if not rows:
            return "pending: no run yet"
        failed = [r["name"] for r in rows if r["status"] == "completed" and r["conclusion"] == "failure"]
        going = [r["name"] for r in rows if r["status"] != "completed"]
        if failed:
            return "red: " + "; ".join(failed)
        if going:
            return "pending: " + ", ".join(going)
        return "green"

    def to_draft(self, n):
        if self.draft_refuse:
            return False, merge.DRAFT_ROUTES
        self.drafts.append(n)
        if n in self.pulls:
            self.pulls[n]["draft"] = True
        return True, ""


class CostHost(merge.Host):
    """The real merge.Host for the cost pin. Its one home of GitHub calls, gh (merge.Host.gh), is answered here, so every call that reaches
    it is one GitHub call, and `calls` keeps each one's route: ("run list", sha), ("GET", rel), ("POST", rel), ("pr ready --undo", n).
    Every read is one page (no Link header), so each read is one call. The judgment, the paging and the draft and comment calls are merge.Host's
    own code; only the answers are scripted. pulls: {number: REST row}. runs_by_sha: {sha: runs}. check_rows: {sha: check-run rows}."""

    def __init__(self, required, pulls, runs_by_sha, check_rows, cwd):
        super().__init__(required=required, base="main", minute=60, now=lambda: tm.FAKE_NOW, pause=lambda s: None, repo=tm.FAKE_REPO, cwd=cwd)
        self.pulls, self.runs_by_sha, self.check_rows = pulls, runs_by_sha, check_rows
        self.calls = []

    def server_now(self):
        return tm.FAKE_NOW

    def gh(self, args, cwd=None, idempotent=False, landed=None):
        if args[:2] == ["run", "list"]:
            sha = args[args.index("--commit") + 1]
            self.calls.append(("run list", sha))
            return 0, json.dumps(self.runs_by_sha.get(sha, []))
        if args[:2] == ["pr", "ready"]:
            self.calls.append(("pr ready --undo", int(args[2])))
            return 0, ""
        if args[0] == "api":
            method, rel = args[args.index("-X") + 1], re.sub(r"^repos/[^/]+/[^/]+/?", "", args[1])
            self.calls.append((method, rel))
            m = re.fullmatch(r"commits/([0-9a-f]+)/(check-runs|status)", rel)
            if method == "GET" and rel == "pulls":
                body = [row for row in self.pulls.values() if row["state"] == "open"]
            elif method == "GET" and m and m.group(2) == "check-runs":
                body = {"check_runs": self.check_rows.get(m.group(1), [])}
            elif method == "GET" and m:
                body = {"statuses": []}
            elif method == "POST" and re.fullmatch(r"issues/\d+/comments", rel):
                body = {"id": 1}
            else:
                raise AssertionError("the sweep made a GitHub call the cost pin does not expect: %s %s" % (method, rel))
            return 0, "HTTP/2.0 200 OK\nContent-Type: application/json\n\n" + json.dumps(body)
        raise AssertionError("the sweep ran a gh call the cost pin does not expect: %s" % (args,))


class IdleSweep(tm.Env):
    """One repo pair with an IdleHost. Pull requests are added with pr(); each sweep is one `merge --draft-idle` run."""

    def setUp(self):
        super().setUp()
        self.host = IdleHost(self.co, self.other)

    def pr(self, n, runs=(), draft=False):
        """Pull request n, non-draft unless `draft`, whose head (sha_of(n)) reads as `runs`. -> its head sha."""
        sha = sha_of(n)
        self.host.pulls[n] = tm.REST.list_item(n, sha, "pr-%d" % n, "main", body="", draft=draft)
        self.host.runs_by_sha[sha] = list(runs)
        return sha

    def sweep(self, host=None):
        """`merge --draft-idle` in this checkout, through `host` (the IdleHost when none). -> (rc, text). An argparse refusal of the flag is an answer too, not a crash."""
        out, err = io.StringIO(), io.StringIO()
        try:
            rc, text = self.run_merge_once("--draft-idle", host=host, stdout=out, stderr=err)
        except SystemExit as e:
            rc, text = (e.code if isinstance(e.code, int) else 1), out.getvalue() + err.getvalue()
        return rc, text

    def assert_sweep_ran(self, rc, text, reads=1):
        self.assertEqual(self.host.pull_list_reads, reads,
                         "merge --draft-idle did not list the open pull requests %d time(s) (rc %s): %s" % (reads, rc, text))

    def assert_nothing_drafted(self, text, why):
        self.assertEqual(self.host.drafts, [], "%s: a PR was drafted: %s" % (why, text))
        self.assertEqual(self.host.posted, [], "%s: a comment was posted: %s" % (why, text))

    def test_idle_red_pr_goes_back_to_draft_and_gets_one_comment_that_says_why(self):
        sha = self.pr(7, [red(age=3 * HOUR)])
        rc, text = self.sweep()
        self.assert_sweep_ran(rc, text)
        self.assertEqual(rc, 0, "the sweep exited %s with a drafted PR: %s" % (rc, text))
        self.assertEqual(self.host.drafts, [7], "the idle red PR #7 was not drafted: " + text)
        self.assertEqual([n for n, _ in self.host.posted], [7], "PR #7 did not get exactly one comment: " + text)
        body = self.host.posted[0][1]
        for needle, what in ((sha, "the head sha"), ("#7", "the PR number"), (RED_JOB, "the red job name"),
                             ("idle 3 h", "the hours idle"), (RULING, "the ruling"), ("merge 7 --ready", "how to return"),
                             ("push", "the fix-and-push step")):
            self.assertIn(needle, body, "the comment misses %s: %s" % (what, body))

    def test_red_pr_exactly_two_hours_idle_goes_back_to_draft(self):
        self.pr(7, [red(age=IDLE_SECONDS)])
        rc, text = self.sweep()
        self.assert_sweep_ran(rc, text)
        self.assertEqual(self.host.drafts, [7], "a red PR idle exactly 2 h was not drafted: " + text)

    def test_red_pr_one_second_short_of_two_hours_stays_ready(self):
        self.pr(7, [red(age=IDLE_SECONDS - 1)])
        rc, text = self.sweep()
        self.assert_sweep_ran(rc, text)
        self.assert_nothing_drafted(text, "a red PR idle 1 h 59 min 59 s")

    def test_red_pr_pushed_one_hour_fifty_nine_minutes_ago_stays_ready(self):
        self.pr(7, [red(age=HOUR + 59 * 60)])
        rc, text = self.sweep()
        self.assert_sweep_ran(rc, text)
        self.assert_nothing_drafted(text, "a red PR idle 1 h 59 min")

    def test_the_newest_run_decides_the_age_not_the_oldest(self):
        self.pr(7, [red(age=3 * HOUR), red(age=HOUR)])
        rc, text = self.sweep()
        self.assert_sweep_ran(rc, text)
        self.assert_nothing_drafted(text, "a head whose newest run is 1 h old, under an older red run of 3 h")

    def test_green_idle_pr_stays_ready(self):
        self.pr(7, [green(age=3 * HOUR)])
        rc, text = self.sweep()
        self.assert_sweep_ran(rc, text)
        self.assert_nothing_drafted(text, "a green PR idle 3 h")

    def test_red_idle_pr_with_a_run_still_going_on_its_head_stays_ready(self):
        self.pr(7, [red(age=3 * HOUR), pending("Deploy preview", age=3 * HOUR)])
        rc, text = self.sweep()
        self.assert_sweep_ran(rc, text)
        self.assert_nothing_drafted(text, "a red PR with a run in progress on its head")

    def test_cancelled_only_idle_pr_stays_ready(self):
        self.pr(7, [cancelled(age=3 * HOUR)])
        rc, text = self.sweep()
        self.assert_sweep_ran(rc, text)
        self.assert_nothing_drafted(text, "a PR whose only run was cancelled")

    def test_draft_pr_is_skipped_and_gets_no_comment(self):
        self.pr(7, [red(age=3 * HOUR)], draft=True)
        rc, text = self.sweep()
        self.assert_sweep_ran(rc, text)
        self.assert_nothing_drafted(text, "a PR that is already a draft")

    def test_pr_with_no_runs_at_all_stays_ready(self):
        self.pr(7, [])
        rc, text = self.sweep()
        self.assert_sweep_ran(rc, text)
        self.assert_nothing_drafted(text, "a PR with no runs on its head")

    def test_failed_runs_read_leaves_that_pr_alone_and_says_unknown_while_the_rest_is_swept(self):
        self.pr(7, [red(age=3 * HOUR)])
        self.pr(8, [red(age=3 * HOUR)])
        self.host.runs_fail[sha_of(7)] = "gh run list failed: HTTP 502"
        rc, text = self.sweep()
        self.assert_sweep_ran(rc, text)
        self.assertEqual(self.host.drafts, [8], "PR #8, whose runs read, was not drafted, or PR #7 was: " + text)
        self.assertIn("unknown", text, "the failed runs read of PR #7 is not printed as unknown: " + text)
        self.assertIn("#7", text, "the unknown line does not name PR #7: " + text)

    def test_failed_open_list_read_drafts_nothing_and_exits_nonzero(self):
        self.pr(7, [red(age=3 * HOUR)])
        self.host.list_fail = "gh api pulls failed: HTTP 502"
        rc, text = self.sweep()
        self.assert_sweep_ran(rc, text)
        self.assertNotEqual(rc, 0, "a failed open-list read exited 0: " + text)
        self.assertIn("unknown", text, "the failed open-list read is not printed as unknown: " + text)
        self.assert_nothing_drafted(text, "the open list did not read")

    def test_empty_open_list_drafts_nothing_and_counts_zero(self):
        rc, text = self.sweep()
        self.assert_sweep_ran(rc, text)
        self.assertEqual(rc, 0, "an empty sweep exited %s: %s" % (rc, text))
        self.assert_nothing_drafted(text, "no open pull requests")
        self.assertRegex(text, r"\bdrafted 0\b", "the summary does not count 0 drafted: " + text)

    def test_mixed_sweep_drafts_each_idle_red_pr_and_no_other(self):
        for n in (7, 8, 9, 10):
            self.pr(n, [red(age=3 * HOUR)])
        self.pr(11, [green(age=3 * HOUR)])
        self.pr(12, [red(age=IDLE_SECONDS - 1)])
        self.pr(13, [red(age=3 * HOUR)], draft=True)
        self.pr(14, [])
        self.pr(15, [red(age=3 * HOUR), pending("Deploy preview", age=3 * HOUR)])
        rc, text = self.sweep()
        self.assert_sweep_ran(rc, text)
        self.assertEqual(self.host.drafts, [7, 8, 9, 10], "the mixed sweep drafted the wrong PRs: " + text)
        self.assertEqual([n for n, _ in self.host.posted], [7, 8, 9, 10], "the mixed sweep commented on the wrong PRs: " + text)
        self.assertRegex(text, r"\bdrafted 4\b", "the summary does not count 4 drafted: " + text)

    def cost_sweep(self, required, rows):
        """One `merge --draft-idle` through a CostHost of `required` (a list of check names, or "none"), over the REST rows {number: (row, runs, check rows)}.
        -> (the host, its text). The environment names that route a cloud session takes are stripped: the local `gh pr ready --undo` is the route counted."""
        pulls = {n: r for n, (r, _, _) in rows.items()}
        runs = {r["head"]["sha"]: rr for r, rr, _ in rows.values()}
        checks = {r["head"]["sha"]: cr for r, _, cr in rows.values()}
        host = CostHost(required, pulls, runs, checks, self.co)
        with unittest.mock.patch.dict(os.environ):
            os.environ.pop("CLAUDE_CODE_REMOTE", None)
            os.environ.pop("GH_REPO", None)
            rc, text = self.sweep(host=host)
        self.assertEqual(rc, 0, "the cost sweep exited %s: %s" % (rc, text))
        return host, text

    def test_cost_per_non_draft_pr_is_one_run_list_and_two_checks_page_reads_under_a_pinned_list(self):
        sha7, sha8, sha9 = sha_of(7), sha_of(8), sha_of(9)
        rows = {
            7: (tm.REST.list_item(7, sha7, "pr-7", "main", body="", draft=False), [red(age=3 * HOUR)], [tm.draft_row(RED_JOB, "failure")]),
            8: (tm.REST.list_item(8, sha8, "pr-8", "main", body="", draft=False), [green(age=3 * HOUR)], [tm.draft_row(RED_JOB, "success")]),
            9: (tm.REST.list_item(9, sha9, "pr-9", "main", body="", draft=True), [red(age=3 * HOUR)], [tm.draft_row(RED_JOB, "failure")]),
        }
        host, text = self.cost_sweep([RED_JOB], rows)
        calls = host.calls
        self.assertEqual(calls.count(("GET", "pulls")), 1, "the sweep did not read the open list once: %s" % calls)
        for sha in (sha7, sha8):
            self.assertEqual(calls.count(("run list", sha)), 1, "head %s was not read through the run list once: %s" % (sha, calls))
            self.assertEqual(calls.count(("GET", "commits/%s/check-runs" % sha)), 1, "head %s did not read its check runs once: %s" % (sha, calls))
            self.assertEqual(calls.count(("GET", "commits/%s/status" % sha)), 1, "head %s did not read its statuses once: %s" % (sha, calls))
        self.assertEqual([c for c in calls if sha9 in str(c)], [], "the draft PR #9 was read, and a draft costs nothing: %s" % calls)
        self.assertEqual(calls.count(("pr ready --undo", 7)), 1, "the red idle PR #7 was not drafted once: " + text)
        self.assertEqual(calls.count(("POST", "issues/7/comments")), 1, "the drafted PR #7 did not get one comment: " + text)
        self.assertEqual(len(calls), 9, "the sweep made %d GitHub calls, and the cost pin names 9 (1 open list, 3 per non-draft PR, 2 for the draft): %s" % (len(calls), calls))

    def test_cost_under_none_is_one_run_list_per_non_draft_pr_and_no_checks_read(self):
        sha7, sha8 = sha_of(7), sha_of(8)
        rows = {
            7: (tm.REST.list_item(7, sha7, "pr-7", "main", body="", draft=False), [red(age=3 * HOUR)], []),
            8: (tm.REST.list_item(8, sha8, "pr-8", "main", body="", draft=False), [green(age=3 * HOUR)], []),
        }
        host, text = self.cost_sweep("none", rows)
        calls = host.calls
        self.assertEqual(calls.count(("GET", "pulls")), 1, "the sweep did not read the open list once: %s" % calls)
        for sha in (sha7, sha8):
            self.assertEqual(calls.count(("run list", sha)), 1, "head %s was not read through the run list once under none: %s" % (sha, calls))
        self.assertEqual([c for c in calls if c[0] == "GET" and c[1].startswith("commits/")], [], "a checks page was read under none, which reads no check: %s" % calls)
        self.assertEqual(calls.count(("pr ready --undo", 7)), 0, "under none the red PR #7 was drafted, though none reads no check: " + text)
        self.assertEqual(len(calls), 3, "the sweep made %d GitHub calls under none, and the cost pin names 3 (1 open list, 1 run list per non-draft PR): %s" % (len(calls), calls))

    def test_second_sweep_posts_no_second_comment(self):
        self.pr(7, [red(age=3 * HOUR)])
        rc, text = self.sweep()
        self.assert_sweep_ran(rc, text)
        self.assertEqual(self.host.drafts, [7], "precondition: the first sweep did not draft PR #7: " + text)
        rc, text = self.sweep()
        self.assert_sweep_ran(rc, text, reads=2)
        self.assertEqual(len(self.host.posted), 1, "a second sweep posted another comment: %s" % self.host.posted)

    def test_cloud_route_posts_no_comment_that_says_the_pr_returned_to_draft(self):
        self.pr(7, [red(age=3 * HOUR)])
        self.host.draft_refuse = True
        rc, text = self.sweep()
        self.assert_sweep_ran(rc, text)
        self.assertIn(sha_of(7), self.host.runs_reads, "the runs of PR #7 were not read, so nothing was judged: " + text)
        self.assertEqual(self.host.drafts, [], "a cloud host drafted PR #7: " + text)
        for n, body in self.host.posted:
            self.assertNotIn("returned to draft", body.lower(),
                             "a comment on #%s says the PR returned to draft, and this host did not draft it: %s" % (n, body))

    def test_cloud_route_leaves_the_pr_unknown_so_a_clash_still_counts_it_as_ready(self):
        self.pr(7, [red(age=3 * HOUR)])
        self.host.draft_refuse = True
        said = []
        verdict = merge.idle_prs_module().draft_one(self.host, 7, self.host.pulls[7], self.host.now(), said.append,
                                                    (merge.Stop, OSError), merge.DRAFT_ROUTES)
        self.assertNotIn(verdict, ("drafted", "route"),
                         "a cloud route reads as drafted, so a clash drops PR #7 as not ready: verdict %r, %s" % (verdict, said))

    def test_cloud_route_is_reported_as_unknown_and_not_drafted_in_the_sweep(self):
        self.pr(7, [red(age=3 * HOUR)])
        self.host.draft_refuse = True
        rc, text = self.sweep()
        self.assert_sweep_ran(rc, text)
        self.assertEqual(self.host.drafts, [], "a cloud host drafted PR #7: " + text)
        self.assertRegex(text, r"\bdrafted 0\b", "the summary counts a drafted PR on a cloud route: " + text)
        lines = [line for line in text.splitlines() if "#7" in line]
        self.assertTrue(any("unknown" in line or "not done" in line for line in lines),
                        "the cloud route for PR #7 is not reported as unknown or not done: " + text)

    def test_age_is_read_on_github_clock_not_a_local_clock_three_hours_ahead(self):
        self.pr(7, [red(age=30 * 60)])
        self.host.local_now = tm.FAKE_NOW + 3 * HOUR
        rc, text = self.sweep()
        self.assert_sweep_ran(rc, text)
        self.assert_nothing_drafted(text, "a red PR pushed 30 min ago by GitHub's clock, with the local clock 3 h ahead")

    def test_age_is_read_on_github_clock_not_a_local_clock_three_hours_behind(self):
        self.pr(7, [red(age=2 * HOUR + 30 * 60)])
        self.host.local_now = tm.FAKE_NOW - 3 * HOUR
        rc, text = self.sweep()
        self.assert_sweep_ran(rc, text)
        self.assertEqual(self.host.drafts, [7], "a red PR idle 2 h 30 min by GitHub's clock was not drafted, with the local clock 3 h behind: " + text)

    def test_unread_github_clock_leaves_the_pr_ready_and_does_not_use_the_local_clock(self):
        self.pr(7, [red(age=3 * HOUR)])
        self.host.github_now = None
        rc, text = self.sweep()
        self.assert_sweep_ran(rc, text)
        self.assert_nothing_drafted(text, "a red PR idle 3 h by the local clock, with GitHub's clock unread")

    def test_draft_that_lands_before_a_failed_comment_is_reported_as_drafted_comment_failed(self):
        self.pr(7, [red(age=3 * HOUR)])
        self.host.comment_fail = "gh api issues/7/comments failed: HTTP 502"
        rc, text = self.sweep()
        self.assert_sweep_ran(rc, text)
        self.assertEqual(self.host.drafts, [7], "precondition: the draft of PR #7 did not land: " + text)
        lines = [line for line in text.splitlines() if "#7" in line]
        self.assertTrue(any("drafted, comment failed" in line for line in lines),
                        "PR #7 was drafted and its comment failed, but the line does not say so: " + text)
        self.assertFalse(any("left as it is" in line for line in lines), "PR #7 is said to be left as it is, though its draft landed: " + text)


DATE_TEXT = "Mon, 23 Nov 2026 20:00:00 GMT"  # the Date header GitHub sends for the instant DATE_EPOCH names
DATE_EPOCH = calendar.timegm((2026, 11, 23, 20, 0, 0))  # that instant in epoch seconds: timegm reads the fields as UTC, never as the local zone
ZONES = ("America/Chicago", "Asia/Kolkata") if hasattr(time, "tzset") else ("",)  # one local zone behind UTC and one ahead; "" runs in the current zone


@contextlib.contextmanager
def in_zone(zone):
    """Run the block with TZ set to `zone`, then put TZ back. An empty zone, or a platform with no time.tzset, runs the block as it is."""
    if not zone or not hasattr(time, "tzset"):
        yield
        return
    old = os.environ.get("TZ")
    os.environ["TZ"] = zone
    time.tzset()
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = old
        time.tzset()


def make_host(now=tm.FAKE_NOW, cwd=None, required=("checks",)):
    """A real merge.Host, no method overridden, whose local clock is `now`. A server_now that returns the local clock fails against it."""
    return merge.Host(required=list(required), base="main", minute=60, now=lambda: now, pause=lambda s: None, repo=tm.FAKE_REPO, cwd=cwd)


def reply(date=None):
    """A 200 `gh api -i` reply as gh prints it: the status line and headers, a Date header when `date` is given, then the body."""
    return (0, tm.gh_i(200, '{"login": "o"}', **({"Date": date} if date is not None else {})))


def answer(test, host, *replies):
    """Answer each of `host`'s next gh calls with the next of `replies` (the last one again), at merge.sh, the seam RateLimitWait.replies
    patches. Each call is `gh api -i`, so Host.gh reads the header block of its reply as it does in production."""
    tm.RateLimitWait.replies(test, *replies)
    for _ in replies:
        host.gh(["api", "repos/owner/repo/pulls", "-i"])


class GitHubDateHeader(unittest.TestCase):
    """Host.server_now reads GitHub's clock from the Date header of the newest `gh api -i` reply that had a header block (Host.note_budget).
    Only the gh answers are scripted; Host's own methods run. The local clock is tm.FAKE_NOW, never the Date."""

    def test_a_date_header_reads_as_the_instant_it_names_in_every_local_zone(self):
        for zone in ZONES:
            with self.subTest(zone=zone or "current zone"), in_zone(zone):
                host = make_host()
                answer(self, host, reply(DATE_TEXT))
                self.assertEqual(host.server_now(), DATE_EPOCH,
                                 f"the Date header {DATE_TEXT!r} did not read as the instant it names: server_now() is {host.server_now()!r}, expected {DATE_EPOCH}")

    def test_a_reply_with_headers_and_no_date_leaves_the_clock_unread(self):
        host = make_host()
        answer(self, host, reply(DATE_TEXT))
        self.assertEqual(host.server_now(), DATE_EPOCH, "precondition: the Date reply did not set GitHub's clock, so the None below would prove nothing")
        answer(self, host, reply(None))
        self.assertIsNone(host.server_now(), f"a reply with a header block and no Date header set GitHub's clock to {host.server_now()!r}, not None")

    def test_a_reply_with_no_header_block_keeps_the_clock_read_last(self):
        host = make_host()
        answer(self, host, reply(DATE_TEXT))
        self.assertEqual(host.server_now(), DATE_EPOCH, "precondition: the Date reply did not set GitHub's clock, so the kept value below would prove nothing")
        answer(self, host, (0, "[]"))  # a `-i` reply that starts with no status line: note_budget reads no headers from it
        self.assertEqual(host.server_now(), DATE_EPOCH, f"a reply with no header block moved GitHub's clock to {host.server_now()!r}")

    def test_before_any_reply_the_clock_is_unread(self):
        host = make_host()
        self.assertIsNone(host.server_now(), f"a host that has read no reply reports GitHub's clock as {host.server_now()!r}, not None")


class GitHubDateZoneOffset(unittest.TestCase):
    """A Date written `-0000` says UTC and that the local offset is unknown (RFC 2822): it names the same instant as the GMT form. email.utils
    parses `-0000` as a naive datetime, and a naive .timestamp() reads it as local time, so the instant moves with the zone. Red until the
    parse reads the `-0000` form as UTC."""

    def test_a_date_written_with_offset_minus_zero_reads_as_the_same_utc_instant(self):
        for zone in ZONES:
            with self.subTest(zone=zone or "current zone"), in_zone(zone):
                host = make_host()
                answer(self, host, reply("Mon, 23 Nov 2026 20:00:00 -0000"))
                self.assertEqual(host.server_now(), DATE_EPOCH,
                                 f"a Date ending -0000 read as local time, not UTC, in zone {zone or 'current'}: server_now() is {host.server_now()!r}, expected {DATE_EPOCH}")


class GitHubDateSweep(tm.Env):
    """`merge --draft-idle` through the real merge.Host, its gh calls answered by the fake gh on PATH (test_merge.FAKE_GH_PR). GitHub's clock is
    the Date header of the fake's replies (DATE_TEXT); the local clock runs 3 h ahead of it. The PR's one red run is 30 min old by GitHub's
    clock, so the PR is kept. Counted from the local clock, the same run is 3 h 30 min old: idle, and drafted."""

    def setUp(self):
        super().setUp()
        tm.install_gh_shim(self)

    def test_a_red_run_30_min_old_by_githubs_date_is_kept_though_the_local_clock_runs_3_h_ahead(self):
        created = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(DATE_EPOCH - 30 * 60))
        tm.GhHalf.set(self, open_prs=[["feat", self.head("feat"), "main", 7]], checks_seq=[[(RED_JOB, "fail", "https://x/y")]],
                      runs_seq=[[(RED_JOB, "completed", "failure")]], date=DATE_TEXT, runs_created=created)
        host = make_host(now=DATE_EPOCH + 3 * HOUR, cwd=self.co, required=[RED_JOB])
        with unittest.mock.patch.dict(os.environ):
            os.environ.pop("CLAUDE_CODE_REMOTE", None)
            os.environ.pop("GH_REPO", None)
            rc, text = self.run_merge_once("--draft-idle", host=host)
        calls = tm.GhHalf.calls(self)
        self.assertIn("run list", calls, "the red head's runs were not read, so PR #7 was not judged: " + text)  # scope first
        self.assertEqual(host.server_now(), DATE_EPOCH, f"GitHub's clock is not the Date header of the replies: server_now() is {host.server_now()!r}: " + text)
        self.assertRegex(text, r"\bkept 1\b", "PR #7 was not kept, though its newest run is 30 min old by GitHub's clock: " + text)
        self.assertNotIn("pr ready", calls, "PR #7 was drafted, which counts its age from the local clock 3 h ahead: " + text)


if __name__ == "__main__":
    unittest.main()
