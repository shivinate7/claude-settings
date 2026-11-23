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

Cost pin: one open-pulls read per sweep, and at most one runs read per non-draft PR. No file is written, and no timer is started.
Not pinned here: a PR a person readies again with no push and that goes red and idle again. The sweep then drafts it, and a
second comment is not blocked by a comment read. That is an open design question for the report, not a case.

Each case runs the sweep first, then asserts its outcome, so a must-not case is never a pass on a missing entry. Each failure message
names one cause.
"""
import io
import itertools
import os
import sys
import time
import unittest

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

    def sweep(self):
        """`merge --draft-idle` in this checkout. -> (rc, text). An argparse refusal of the flag is an answer too, not a crash."""
        out, err = io.StringIO(), io.StringIO()
        try:
            rc, text = self.run_merge_once("--draft-idle", stdout=out, stderr=err)
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

    def test_cost_one_list_read_and_at_most_one_runs_read_per_non_draft_pr(self):
        self.pr(7, [red(age=3 * HOUR)])
        self.pr(8, [green(age=3 * HOUR)])
        self.pr(9, [red(age=3 * HOUR)], draft=True)
        rc, text = self.sweep()
        self.assert_sweep_ran(rc, text)
        self.assertEqual(sorted(self.host.runs_reads), sorted([sha_of(7), sha_of(8)]),
                         "the runs reads are not one per non-draft PR: %s" % self.host.runs_reads)

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


if __name__ == "__main__":
    unittest.main()
