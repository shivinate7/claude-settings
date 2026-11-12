#!/usr/bin/env python3
"""Fixture suite for the PR ledger (decision pr-ledger, part 1, in merge/merge.py): `merge --reviewed` gives each open pull request one
next act, and prints two gold-0 numbers.

Run: python3 merge/test_pr_ledger.py

The ledger reads GitHub alone: the open pull requests (with their labels and bodies), the repo's comments, and each labelled pull
request's label events. Each case runs `merge --reviewed` over the scripted host of merge/test_merge.py (PullsHost, one home) and reads
the output a reader reads. The clock is Host.now, held at NOW, so no case reads the real clock or sleeps.

THE OUTPUT CONTRACT these cases read (merge.py builds it):
  one line per open pull request, starting `#<n> <branch> <sha9> `. Its review state stays as it is today. Before `; CI` it carries
    `; next: <act>, owner <owner>, age <H>h` and `, RED` after the age when the act is red.
    <act> is one of: batch | lane round <n> | fix check | fresh full review | waits on <item> | batch run | blocked on #<n> | lane lint | none
    `lane lint` (owner lane) is a done record with no lane-lint PASS at its head; `lane` is accepted too.
  after the lines, two numbers, each on its own line:
    `longest wait from a done record: <H>h`
    `open PRs with no next act: <N>`

Each red case fails on the current merge.py at its act or number assert. Where the fixture gives the pull request a line today, a
control assert reads that line's state first. A pull request with no line today has no next act, so the scope assert (one line
for it) runs before the act is read. The no-write case passes on the current code: it guards the cost the record states.
The cases of NextActGaps, and the lane-lint and held-draft greens of NextActShapes, pass on the current code: each guards a rule
the fix for the reds must keep.
"""
import calendar
import os
import re
import sys
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_merge as tm  # noqa: E402  the review-record fixtures, PullsHost and ReviewEnv (one home); importing it runs none of its cases

NOW = calendar.timegm((2026, 11, 12, 12, 0, 0))  # the clock of every case: Host.now, so an age is a fixed number of hours
LIVE, OLD, OTHER = tm.REVIEW_HEAD, tm.REVIEW_OLD_HEAD, "3c" * 20  # the live head, an older head, and a head no record names
NEXT_PART = re.compile(r"; next: (?P<act>[^;]+?), owner (?P<owner>[^,;]+), age (?P<age>[^,;]+?)(?P<red>, RED)?(?=;|$)")
LONGEST_LINE = re.compile(r"^longest wait from a done record: (?P<hours>\d+(?:\.\d+)?)h$", re.M)
NO_ACT_LINE = re.compile(r"^open PRs with no next act: (?P<count>\d+)$", re.M)


def iso(hours_ago):
    """The GitHub timestamp `hours_ago` hours before NOW."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW - hours_ago * 3600))


def pull(n, head=LIVE, *, draft=False, labels=(), body="", hours_ago=2, base="main"):
    """An open pull request as `pages("pulls")` lists it: its labels and body, and its created and updated times `hours_ago` before NOW."""
    d = tm.batch_pull(n, head, base=base, draft=draft, created_at=iso(hours_ago))
    return {**d, "updated_at": iso(hours_ago), "body": body, "labels": [{"name": name} for name in labels]}


def record(n, hours_ago=3, rounds=tm.REVIEW_PASS, head=LIVE, fix=(), grant=(), guard="no"):
    """The review record comment of pull request n, posted `hours_ago` before NOW. `grant` holds its Grant line, which lets one round past the cap read."""
    return tm.review_comment(1000 + n, n, tm.record_text(rounds=rounds, head=head, n=n, fix=fix, grant=grant, guard=guard), created=iso(hours_ago))


def lint(n, head=LIVE):
    """The lane-lint PASS of pull request n at `head`: a done record reads done only with it (decision lanes-run-no-full-ci-job)."""
    return tm.lint_of(n, head)


def note(n, text, hours_ago=5):
    """A plain comment on pull request n. A held pull request's `Waits on:` line is one."""
    return tm.review_comment(2000 + n, n, text + "\n", created=iso(hours_ago))


def event(name, hours_ago, action="labeled"):
    """A label event of a pull request, as `issues/<n>/events` lists it, oldest first in a list."""
    return {"event": action, "label": {"name": name}, "created_at": iso(hours_ago)}


class LedgerHost(tm.PullsHost):
    """PullsHost that also serves each pull request's label events (`issues/<n>/events`), on both seams: pages() and gh's answer.
    `event_reads` keeps the number of each events list read, in order. The clock is NOW (Host.now)."""

    def __init__(self, pulls, comments=(), events=None, count_gh=False, **reads):
        super().__init__(pulls, {}, comments=comments, count_gh=count_gh, **reads)
        self.events, self.event_reads = events or {}, []
        self.now = lambda: NOW

    def pages(self, rel, key=None, fields=None):
        m = re.fullmatch(r"issues/(\d+)/events", rel)
        if m and not self.count_gh:
            self.event_reads.append(int(m.group(1)))
            return list(self.events.get(int(m.group(1)), []))
        return super().pages(rel, key, fields)

    def answer(self, rel, argv):
        m = re.fullmatch(r"issues/(\d+)/events", rel)
        if not m and rel != "pulls":
            return super().answer(rel, argv)
        _method, _path, params, flags, _jq = tm.REST.parse(argv)
        if rel == "pulls":
            return self.paged(self.pulls, rel, params, flags)
        self.event_reads.append(int(m.group(1)))
        return tm.REST.listing(self.events.get(int(m.group(1)), []), None, params, flags, None, 100)

    def paged(self, items, rel, params, flags):
        """The reply of one page of a list read under -i: a Link header with rel="next" while pages follow, as gh prints it (PullsHost.files_reply's
        form). Without it Host.pages stops after the first page, which a full-size fixture would not show."""
        text = tm.REST.listing(items, None, params, flags, None, 100)
        size = max(1, min(int(params.get("per_page", 30)), 100))
        page, last = int(params.get("page", 1)), max(1, -(-len(items) // size))
        if "include" not in flags or "paginate" in flags or page >= last:
            return text
        link = '<https://api.github.com/repos/{owner}/{repo}/%s?page=%d>; rel="next"' % (rel, page + 1)
        return "HTTP/1.1 200 OK\nLink: %s\n\n%s" % (link, text)


class LedgerCase(tm.ReviewEnv):
    """The `merge --reviewed` read of a scripted host, and the readers of its output. No test lives here."""

    def reviewed(self, host):
        """-> the output of `merge --reviewed` over `host`, which must exit 0."""
        rc, out, err = self.run_args("--reviewed", host=host)
        self.assertEqual(rc, 0, out + err)
        return out

    def line_of(self, out, n):
        """-> the one line of pull request n. Scope first: a pull request with no line of its own has no next act to read."""
        lines = [l for l in out.splitlines() if l.startswith(f"#{n} ")]
        self.assertEqual(len(lines), 1, f"#{n} has no line of its own, so the output names no next act for it:\n{out}")
        return lines[0]

    def next_part(self, out, n):
        """-> (act, owner, red) of pull request n, read from the `next:` part of its line."""
        line = self.line_of(out, n)
        m = NEXT_PART.search(line)
        self.assertIsNotNone(m, f"#{n}'s line has no `next:` part, so it names no next act:\n{line}")
        return m.group("act"), m.group("owner"), m.group("red") is not None

    def next_act(self, out, n):
        """-> (act, red) of pull request n, read from the `next:` part of its line."""
        act, _owner, red = self.next_part(out, n)
        return act, red


class NextActReds(LedgerCase):
    """The reds of decision pr-ledger's cost record, one per named case, each after its control."""

    def test_a_non_draft_pr_with_no_record_has_no_next_act_and_reads_red(self):
        out = self.reviewed(LedgerHost([pull(7, hours_ago=5)]))
        act, red = self.next_act(out, 7)
        self.assertEqual(act, "none", f"#7 is not a draft and has no record, so no rule gives it an act:\n{out}")
        self.assertTrue(red, f"#7 has no next act, and its line does not read RED:\n{out}")

    def test_a_done_record_for_an_older_head_is_never_batched_and_reads_fix_verifier(self):
        host = LedgerHost([pull(7)], comments=[record(7, 10, head=OLD)], commits={LIVE: [OLD]})
        out = self.reviewed(host)
        self.assertRegex(self.line_of(out, 7), rf"^#7 feat7 {LIVE[:9]} stale: ", "control: #7's record does not read stale at the live head")
        act, _red = self.next_act(out, 7)
        self.assertEqual(act, "fix check", f"#7's record is for {OLD[:9]}, the live head is {LIVE[:9]}, and it has no Fix check line:\n{out}")

    def test_a_done_record_older_than_one_batch_cycle_reads_batch_and_red(self):
        out = self.reviewed(LedgerHost([pull(7)], comments=[record(7, 30), lint(7)]))
        self.assertRegex(self.line_of(out, 7), rf"^#7 feat7 {LIVE[:9]} done: ", "control: #7's record does not read done at the live head")
        act, red = self.next_act(out, 7)
        self.assertEqual(act, "batch", f"#7 is done at the live head, so its act is batch:\n{out}")
        self.assertTrue(red, f"#7 has waited 30 h for a batch, past the 24 h limit, and its line does not read RED:\n{out}")

    def test_a_batch_run_older_than_one_batch_cycle_reads_red(self):
        host = LedgerHost([pull(7, labels=["batch"], hours_ago=40)], events={7: [event("batch", 30)]})
        out = self.reviewed(host)
        act, red = self.next_act(out, 7)
        self.assertEqual(act, "batch run", f"#7 carries the batch label on an integration PR, so its act is batch run:\n{out}")
        self.assertTrue(red, f"#7's batch label is 30 h old, past the 24 h limit, and its line does not read RED:\n{out}")

    def test_a_held_pr_with_no_waits_line_reads_red(self):
        host = LedgerHost([pull(7, labels=["held"])], events={7: [event("held", 5)]})
        out = self.reviewed(host)
        act, red = self.next_act(out, 7)
        self.assertEqual(act, "none", f"#7 is held with no `Waits on:` line, so no hold rule gives it an act:\n{out}")
        self.assertTrue(red, f"#7 is held with no `Waits on:` line, and its line does not read RED:\n{out}")

    def test_a_held_pr_whose_waits_line_names_no_debt_or_page_reads_red(self):
        host = LedgerHost([pull(7, labels=["held"])], comments=[note(7, "Waits on: someone")], events={7: [event("held", 5)]})
        out = self.reviewed(host)
        act, red = self.next_act(out, 7)
        self.assertTrue(red, f"#7's Waits line names no debt or page item, so it does not hold the PR and must read RED:\n{out}")

    def test_an_idle_draft_past_its_72_h_limit_reads_red(self):
        out = self.reviewed(LedgerHost([pull(9, draft=True, hours_ago=80)]))
        act, red = self.next_act(out, 9)
        self.assertEqual(act, "lane round 1", f"#9 is a draft with no record, so its act is lane round 1:\n{out}")
        self.assertTrue(red, f"#9 has been a draft with no record for 80 h, past the 72 h limit, and its line does not read RED:\n{out}")

    def test_a_body_line_naming_a_base_does_not_stack_the_pr_and_reads_none_red(self):
        for body in ("Based on #5", "Stacked on #5"):
            with self.subTest(body=body):
                out = self.reviewed(LedgerHost([pull(7, body=f"{body}\n\nThe rest of the change.", hours_ago=5), pull(5, draft=True, hours_ago=2)]))
                act, red = self.next_act(out, 7)
                self.assertEqual(act, "none", f"#7 is based on main, and `{body}` in its body does not stack it; only its base ref does:\n{out}")
                self.assertTrue(red, f"#7 has no next act, and its line does not read RED:\n{out}")

    def test_a_fix_verifier_older_than_72_h_reads_red(self):
        host = LedgerHost([pull(7)], comments=[record(7, 80, head=OLD)], commits={LIVE: [OLD]})
        out = self.reviewed(host)
        self.assertRegex(self.line_of(out, 7), rf"^#7 feat7 {LIVE[:9]} stale: ", "control: #7's record does not read stale at the live head")
        act, red = self.next_act(out, 7)
        self.assertEqual(act, "fix check", f"control: #7's record is for {OLD[:9]} and has no Fix check line:\n{out}")
        self.assertTrue(red, f"#7's fix check has waited 80 h, past the 72 h limit, and its line does not read RED:\n{out}")

    def test_a_fresh_full_review_older_than_72_h_reads_red(self):
        fix = tm.fix_verifier_line("FAIL", head=OTHER)
        host = LedgerHost([pull(7)], comments=[record(7, 80, head=OLD, fix=(fix,))], commits={LIVE: [OLD]})
        out = self.reviewed(host)
        self.assertRegex(self.line_of(out, 7), rf"^#7 feat7 {LIVE[:9]} stale: ", "control: #7's record does not read stale at the live head")
        act, red = self.next_act(out, 7)
        self.assertEqual(act, "fresh full review", f"control: #7's fix check failed, so one fresh full review is owed:\n{out}")
        self.assertTrue(red, f"#7's fresh full review has waited 80 h, past the 72 h limit, and its line does not read RED:\n{out}")

    def test_a_lane_round_2_or_later_older_than_72_h_reads_red(self):
        fail1, fail2 = "Round 1: reviewer, sonnet, FAIL", "Round 2: reviewer, sonnet, FAIL"
        for rounds, act_want in (((fail1,), "lane round 2"), ((fail1, fail2), "lane round 3")):
            with self.subTest(act=act_want):
                out = self.reviewed(LedgerHost([pull(7)], comments=[record(7, 80, rounds=rounds)]))
                act, red = self.next_act(out, 7)
                self.assertEqual(act, act_want, f"control: #7's record has {len(rounds)} failed round(s), so {act_want} is owed:\n{out}")
                self.assertTrue(red, f"{act_want} has waited 80 h, past the 72 h limit, and its line does not read RED:\n{out}")

    def test_a_done_record_with_no_lint_pass_reads_lane_not_batch(self):
        out = self.reviewed(LedgerHost([pull(7)], comments=[record(7, 3)]))
        self.assertRegex(self.line_of(out, 7), rf"^#7 feat7 {LIVE[:9]} no lint: .*Run `merge --lane-lint 7`",
                         "control: #7's line does not name merge --lane-lint 7 for a done record with no lint PASS")
        act, owner, _red = self.next_part(out, 7)
        self.assertIn(act, ("lane", "lane lint"), f"#7 is done at the live head, but no lane-lint PASS names that head, so its act is the lane's, not batch:\n{out}")
        self.assertEqual(owner, "lane", f"#7's act is the lane's, so its owner is lane, not batch runner:\n{out}")

    def test_a_done_record_with_no_lint_older_than_72_h_reads_lane_lint_and_red(self):
        out = self.reviewed(LedgerHost([pull(7, hours_ago=120)], comments=[record(7, 100)]))
        self.assertRegex(self.line_of(out, 7), rf"^#7 feat7 {LIVE[:9]} no lint: ", "control: #7's record does not read no lint at the live head")
        act, owner, red = self.next_part(out, 7)
        self.assertEqual(act, "lane lint", f"#7 is done at the live head with no lane-lint PASS, so its act is lane lint:\n{out}")
        self.assertEqual(owner, "lane", f"#7's act is lane lint, so its owner is the lane:\n{out}")
        self.assertTrue(red, f"#7's lane lint has waited 100 h, past the 72 h limit, and its line does not read RED:\n{out}")

    def test_the_longest_wait_counts_a_done_record_with_no_lint(self):
        out = self.reviewed(LedgerHost([pull(7, hours_ago=120)], comments=[record(7, 100)]))
        self.assertRegex(self.line_of(out, 7), rf"^#7 feat7 {LIVE[:9]} no lint: ", "control: #7's record does not read no lint at the live head")
        m = NO_ACT_LINE.search(out)
        self.assertIsNotNone(m, f"merge --reviewed printed no `open PRs with no next act` line:\n{out}")
        self.assertEqual(int(m.group("count")), 0, f"#7's lane lint is an act, so no open PR has no next act:\n{out}")
        m = LONGEST_LINE.search(out)
        self.assertIsNotNone(m, f"merge --reviewed printed no `longest wait from a done record` line:\n{out}")
        self.assertEqual(float(m.group("hours")), 100.0,
                         f"#7's done record was posted 100 h before now, and its lane lint waits from that record, so the longest wait is 100.0h:\n{out}")

    def test_a_held_draft_with_no_waits_line_reads_red(self):
        for label in ("held", "parked", "replaced"):
            with self.subTest(label=label):
                host = LedgerHost([pull(7, draft=True, labels=[label]), pull(9, draft=True)], events={7: [event(label, 5)]})
                out = self.reviewed(host)
                self.assertEqual(self.next_act(out, 9), ("lane round 1", False),
                                 f"control: #9 is an unlabelled draft with no record, so it reads lane round 1, not RED:\n{out}")
                _act, red = self.next_act(out, 7)
                self.assertTrue(red, f"#7 is a draft labelled {label} with no `Waits on:` line, so no hold rule holds it, and its line does not read RED:\n{out}")


class NextActShapes(LedgerCase):
    """The acts that read green: each rule's act and its age, with no red."""

    def test_a_draft_with_no_record_reads_lane_round_1(self):
        out = self.reviewed(LedgerHost([pull(9, draft=True, hours_ago=2)]))
        act, red = self.next_act(out, 9)
        self.assertEqual(act, "lane round 1", f"#9 is a draft with no record:\n{out}")
        self.assertFalse(red, f"#9 is inside its 72 h limit, and its line reads RED:\n{out}")

    def test_an_open_record_reads_the_next_round_owed(self):
        out = self.reviewed(LedgerHost([pull(7)], comments=[record(7, 3, rounds=("Round 1: reviewer, sonnet, FAIL",))]))
        act, red = self.next_act(out, 7)
        self.assertEqual(act, "lane round 2", f"#7's record fails round 1, so round 2 is the next round owed:\n{out}")
        self.assertFalse(red, f"#7 has no limit on lane round 2, and its line reads RED:\n{out}")

    def test_a_stale_record_with_a_failed_fix_verifier_reads_fresh_full_review(self):
        fix = tm.fix_verifier_line("FAIL", head=OTHER)
        host = LedgerHost([pull(7)], comments=[record(7, 10, head=OLD, fix=(fix,))], commits={LIVE: [OLD]})
        out = self.reviewed(host)
        self.assertRegex(self.line_of(out, 7), rf"^#7 feat7 {LIVE[:9]} stale: ", "control: #7's record does not read stale at the live head")
        act, _red = self.next_act(out, 7)
        self.assertEqual(act, "fresh full review", f"#7's fix check failed, so one fresh full review at the live head is owed:\n{out}")

    def test_a_pr_whose_base_ref_is_an_open_pr_head_reads_blocked_on_it(self):
        out = self.reviewed(LedgerHost([pull(7, base="feat5", hours_ago=5), pull(5, draft=True, hours_ago=2)]))
        act, red = self.next_act(out, 7)
        self.assertEqual(act, "blocked on #5", f"#7's base ref is feat5, the head branch of open #5, so it waits on #5:\n{out}")
        self.assertFalse(red, f"#7 is blocked on #5, which has an act of its own, and its line reads RED:\n{out}")

    def test_a_held_pr_with_a_waits_line_reads_waits_on(self):
        for item in ("debt:merge-flake", "page:ask-mw6sd3zwp1"):
            with self.subTest(item=item):
                host = LedgerHost([pull(7, labels=["held"])], comments=[note(7, f"Waits on: {item}")], events={7: [event("held", 5)]})
                out = self.reviewed(host)
                act, red = self.next_act(out, 7)
                self.assertTrue(act.startswith("waits on"), f"#7 is held with `Waits on: {item}`, so its act is waits on:\n{out}")
                self.assertFalse(red, f"#7 waits on {item}, which has no limit, and its line reads RED:\n{out}")

    def test_an_integration_pr_labelled_batch_reads_batch_run(self):
        out = self.reviewed(LedgerHost([pull(7, labels=["batch"])], events={7: [event("batch", 2)]}))
        act, red = self.next_act(out, 7)
        self.assertEqual(act, "batch run", f"#7 carries the batch label, so its act is batch run:\n{out}")
        self.assertFalse(red, f"#7's batch label is 2 h old, inside the 24 h limit, and its line reads RED:\n{out}")

    def test_batch_run_ages_from_the_last_labeled_event(self):
        events = [event("batch", 30), event("batch", 20, action="unlabeled"), event("batch", 2)]
        out = self.reviewed(LedgerHost([pull(7, labels=["batch"], hours_ago=40)], events={7: events}))
        act, red = self.next_act(out, 7)
        self.assertEqual(act, "batch run", f"#7 carries the batch label, so its act is batch run:\n{out}")
        self.assertFalse(red, f"#7's batch label was last added 2 h ago, inside the 24 h limit, and its line reads RED:\n{out}")

    def test_a_fix_verifier_under_72_h_is_not_red(self):
        host = LedgerHost([pull(7)], comments=[record(7, 10, head=OLD)], commits={LIVE: [OLD]})
        out = self.reviewed(host)
        act, red = self.next_act(out, 7)
        self.assertEqual(act, "fix check", f"#7's record is for {OLD[:9]} and has no Fix check line:\n{out}")
        self.assertFalse(red, f"#7's fix check has waited 10 h, inside the 72 h limit, and its line reads RED:\n{out}")

    def test_a_fresh_full_review_under_72_h_is_not_red(self):
        fix = tm.fix_verifier_line("FAIL", head=OTHER)
        host = LedgerHost([pull(7)], comments=[record(7, 10, head=OLD, fix=(fix,))], commits={LIVE: [OLD]})
        out = self.reviewed(host)
        act, red = self.next_act(out, 7)
        self.assertEqual(act, "fresh full review", f"#7's fix check failed, so one fresh full review is owed:\n{out}")
        self.assertFalse(red, f"#7's fresh full review has waited 10 h, inside the 72 h limit, and its line reads RED:\n{out}")

    def test_a_waits_on_older_than_72_h_is_not_red(self):
        host = LedgerHost([pull(7, labels=["held"])], comments=[note(7, "Waits on: debt:merge-flake")], events={7: [event("held", 500)]})
        out = self.reviewed(host)
        act, red = self.next_act(out, 7)
        self.assertTrue(act.startswith("waits on"), f"control: #7 is held with `Waits on: debt:merge-flake`, so its act is waits on:\n{out}")
        self.assertFalse(red, f"#7 waits on debt:merge-flake, which has no limit of its own, and its line reads RED at 500 h:\n{out}")

    def test_a_done_record_with_a_lint_pass_reads_batch_for_the_batch_runner(self):
        out = self.reviewed(LedgerHost([pull(7)], comments=[record(7, 3), lint(7)]))
        self.assertRegex(self.line_of(out, 7), rf"^#7 feat7 {LIVE[:9]} done: ", "control: #7's record does not read done at the live head")
        act, owner, red = self.next_part(out, 7)
        self.assertEqual(act, "batch", f"#7 is done at the live head with a lane-lint PASS, so its act is batch:\n{out}")
        self.assertEqual(owner, "batch runner", f"#7's act is batch, so its owner is the batch runner:\n{out}")
        self.assertFalse(red, f"#7 is done 3 h ago, inside the 24 h limit, and its line reads RED:\n{out}")

    def test_a_done_record_with_no_lint_under_72_h_reads_lane_lint_and_not_red(self):
        out = self.reviewed(LedgerHost([pull(7, hours_ago=70)], comments=[record(7, 60)]))
        self.assertRegex(self.line_of(out, 7), rf"^#7 feat7 {LIVE[:9]} no lint: ", "control: #7's record does not read no lint at the live head")
        act, red = self.next_act(out, 7)
        self.assertEqual(act, "lane lint", f"#7 is done at the live head with no lane-lint PASS, so its act is lane lint:\n{out}")
        self.assertFalse(red, f"#7's lane lint has waited 60 h, inside the 72 h limit, and its line reads RED:\n{out}")

    def test_a_held_draft_with_a_waits_line_reads_waits_on_and_not_red(self):
        for label in ("held", "parked", "replaced"):
            with self.subTest(label=label):
                host = LedgerHost([pull(7, draft=True, labels=[label])], comments=[note(7, "Waits on: debt:merge-flake")], events={7: [event(label, 5)]})
                out = self.reviewed(host)
                act, red = self.next_act(out, 7)
                self.assertEqual(act, "waits on debt:merge-flake",
                                 f"#7 is a draft labelled {label} with `Waits on: debt:merge-flake`, so its act is waits on that item:\n{out}")
                self.assertFalse(red, f"#7 waits on debt:merge-flake, which has no limit of its own, and its line reads RED:\n{out}")


class NextActGaps(LedgerCase):
    """Gaps in the spec that the current merge.py already holds. Each passes on today's code, so a fix for the reds must keep it."""

    def test_a_waits_line_with_a_note_reads_the_bare_item(self):
        host = LedgerHost([pull(7, labels=["held"])], comments=[note(7, "Waits on: debt:merge-flake (waiting for the lane)")], events={7: [event("held", 5)]})
        out = self.reviewed(host)
        act, red = self.next_act(out, 7)
        self.assertEqual(act, "waits on debt:merge-flake", f"#7 is held with `Waits on: debt:merge-flake (note)`, and the note is not part of the item:\n{out}")
        self.assertFalse(red, f"#7 waits on debt:merge-flake, which has no limit of its own, and its line reads RED:\n{out}")

    def test_a_granted_round_4_older_than_72_h_reads_red(self):
        grant = ("Grant: #7, item 444 a, owner, 2026-11-10 12:00 CST",)
        # a grant parses only with its granted round recorded, and a final round that did not pass on a guard change with its net value owed reads open
        rounds = tm.REVIEW_FAILED_THREE + ("Round 4: reviewer, opus, PASS",)
        out = self.reviewed(LedgerHost([pull(7)], comments=[record(7, 80, rounds=rounds, grant=grant, guard="yes")]))
        self.assertRegex(self.line_of(out, 7), rf"^#7 feat7 {LIVE[:9]} open: ", "control: #7's record does not read open at the live head")
        act, red = self.next_act(out, 7)
        self.assertEqual(act, "lane round 4", f"control: #7's record has a Grant line and round 4 recorded on a guard change, so round 4 is the act:\n{out}")
        self.assertTrue(red, f"#7's lane round 4 has waited 80 h, past the 72 h limit, and its line does not read RED:\n{out}")

    def test_a_pr_blocked_on_a_red_pr_reads_red(self):
        out = self.reviewed(LedgerHost([pull(7, base="feat5", hours_ago=5), pull(5, draft=True, hours_ago=80)]))
        self.assertEqual(self.next_act(out, 5), ("lane round 1", True),
                         f"control: #5 is a draft with no record for 80 h, past its 72 h limit, so it reads RED:\n{out}")
        act, red = self.next_act(out, 7)
        self.assertEqual(act, "blocked on #5", f"#7's base ref is feat5, the head branch of open #5, so it is blocked on #5:\n{out}")
        self.assertTrue(red, f"#7 is blocked on #5, which reads RED, and its line does not read RED:\n{out}")

    def test_a_block_loop_reads_red_on_both_prs(self):
        out = self.reviewed(LedgerHost([pull(7, base="feat8", hours_ago=5), pull(8, base="feat7", hours_ago=5)]))
        for n, on in ((7, 8), (8, 7)):
            with self.subTest(n=n):
                act, red = self.next_act(out, n)
                self.assertEqual(act, f"blocked on #{on}", f"control: #{n}'s base ref is the head of #{on}, so it is blocked on #{on}:\n{out}")
                self.assertTrue(red, f"#{n} is blocked on #{on}, which is blocked on #{n}: a loop with no PR that can move, and its line does not read RED:\n{out}")


class NumberLines(LedgerCase):
    """The two gold-0 numbers, each after a control line that the fixture still gives."""

    def test_the_longest_wait_runs_from_the_done_record_to_now(self):
        out = self.reviewed(LedgerHost([pull(7), pull(8, hours_ago=2)], comments=[record(7, 50), lint(7)]))
        self.assertRegex(self.line_of(out, 7), rf"^#7 feat7 {LIVE[:9]} done: ", "control: #7's record does not read done at the live head")
        m = LONGEST_LINE.search(out)
        self.assertIsNotNone(m, f"merge --reviewed printed no `longest wait from a done record` line:\n{out}")
        self.assertEqual(float(m.group("hours")), 50.0, f"the done record of #7 was posted 50 h before now:\n{out}")

    def test_the_count_names_each_open_pr_with_no_next_act(self):
        out = self.reviewed(LedgerHost([pull(7, hours_ago=5), pull(8, hours_ago=5), pull(9, draft=True, hours_ago=2)]))
        m = NO_ACT_LINE.search(out)
        self.assertIsNotNone(m, f"merge --reviewed printed no `open PRs with no next act` line:\n{out}")
        self.assertEqual(int(m.group("count")), 2, f"#7 and #8 are non-drafts with no record, so two open PRs have no next act:\n{out}")

    def test_the_count_names_a_pr_whose_body_names_a_base_but_whose_base_ref_does_not(self):
        out = self.reviewed(LedgerHost([pull(7, body="Based on #5\n\nThe rest of the change.", hours_ago=5), pull(5, draft=True, hours_ago=2)]))
        self.assertIn("; next: lane round 1, owner lane,", self.line_of(out, 5), "control: #5, a draft with no record, does not read lane round 1")
        m = NO_ACT_LINE.search(out)
        self.assertIsNotNone(m, f"merge --reviewed printed no `open PRs with no next act` line:\n{out}")
        self.assertEqual(int(m.group("count")), 1, f"#7 is based on main, so its `Based on #5` body line does not stack it, and it has no next act:\n{out}")

    def test_the_count_covers_every_page_of_open_pulls(self):
        pulls = [pull(n, hours_ago=5) for n in range(1, 102)]  # 101 pulls: the pulls list reads in two pages of 100
        host = LedgerHost(pulls, count_gh=True)
        out = self.reviewed(host)
        self.assertEqual(host.gh_calls.count("pulls"), 2, "control: the open-pull list was not read in two pages")
        m = NO_ACT_LINE.search(out)
        self.assertIsNotNone(m, f"merge --reviewed printed no `open PRs with no next act` line for 101 open pulls:\n{out[-400:]}")
        self.assertEqual(int(m.group("count")), 101, "the count missed pull requests on the second page of the open-pull list")

    def test_an_empty_run_prints_both_numbers_as_zero(self):
        out = self.reviewed(LedgerHost([]))
        m = LONGEST_LINE.search(out)
        self.assertIsNotNone(m, f"with no open pull request, merge --reviewed printed no `longest wait` line:\n{out}")
        self.assertEqual(float(m.group("hours")), 0.0, out)
        m = NO_ACT_LINE.search(out)
        self.assertIsNotNone(m, f"with no open pull request, merge --reviewed printed no `open PRs with no next act` line:\n{out}")
        self.assertEqual(int(m.group("count")), 0, out)


class LedgerCost(LedgerCase):
    """The cost the record states: label events are read only for the batch and hold rules, and a run writes no file and starts no thread."""

    def test_label_events_are_read_only_for_the_batch_and_hold_rules(self):
        pulls = [pull(7, labels=["batch"]), pull(8, labels=["held"]), pull(9, draft=True), pull(10, body="Stacked on #7"), pull(11)]
        comments = [note(8, "Waits on: debt:merge-flake"), record(11, 3), lint(11)]
        host = LedgerHost(pulls, comments=comments, events={7: [event("batch", 2)], 8: [event("held", 5)]}, count_gh=True)
        out = self.reviewed(host)
        self.assertRegex(self.line_of(out, 11), rf"^#11 feat11 {LIVE[:9]} done: ", "control: #11's record does not read done at the live head")
        event_calls = sorted(c for c in host.gh_calls if c.startswith("issues/") and c.endswith("/events"))
        self.assertEqual(event_calls, ["issues/7/events", "issues/8/events"],
                         "the label events were read for other pull requests, or not read for the batch and hold rules")

    def test_a_run_writes_no_file_and_starts_no_thread(self):
        def tree_state():
            state = []
            for root, _dirs, files in os.walk(self.t):
                for name in files:
                    p = os.path.join(root, name)
                    st = os.stat(p)
                    state.append((p, st.st_size, st.st_mtime_ns))
            return sorted(state)
        host = LedgerHost([pull(7, labels=["batch"]), pull(8, draft=True)], events={7: [event("batch", 2)]})
        before, threads = tree_state(), threading.active_count()
        self.reviewed(host)
        self.assertEqual(tree_state(), before, "a `merge --reviewed` run wrote or changed a file under its folder")
        self.assertEqual(threading.active_count(), threads, "a `merge --reviewed` run started a thread")


if __name__ == "__main__":
    unittest.main()
